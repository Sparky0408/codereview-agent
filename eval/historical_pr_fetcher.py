"""Fetches historical merged PRs with review comments via GitHub GraphQL API."""

import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

GRAPHQL_ENDPOINT = "https://api.github.com/graphql"

# language=graphql
_MERGED_PRS_QUERY = """
query($owner: String!, $name: String!, $cursor: String, $limit: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequests(
      states: MERGED,
      last: $limit,
      before: $cursor,
      orderBy: {field: CREATED_AT, direction: DESC}
    ) {
      pageInfo {
        hasPreviousPage
        startCursor
      }
      nodes {
        number
        title
        mergeCommit {
          oid
          parents(first: 1) {
            nodes {
              oid
            }
          }
        }
        files(first: 100) {
          nodes {
            path
          }
        }
        reviews(first: 50) {
          nodes {
            comments(first: 100) {
              nodes {
                body
                path
                originalLine
              }
            }
          }
        }
      }
    }
  }
}
"""

REST_API_BASE = "https://api.github.com"


@dataclass(frozen=True)
class HumanComment:
    """A line-level review comment left by a human reviewer."""

    body: str
    file_path: str
    line: int


@dataclass
class HistoricalPR:
    """All data needed to replay a merged PR through the eval pipeline."""

    number: int
    title: str
    merge_commit_sha: str
    pre_merge_sha: str
    changed_files: list[tuple[str, str]]
    human_comments: list[HumanComment] = field(default_factory=list)


def _parse_pr_node(node: dict) -> HistoricalPR | None:  # type: ignore[type-arg]
    """Parse a single PR node from the GraphQL response.

    Returns None if the PR has no usable line-level comments or missing data.
    File patches are NOT available via GraphQL; they are hydrated later via REST.
    """
    merge_commit = node.get("mergeCommit")
    if not merge_commit:
        return None

    merge_sha: str = merge_commit["oid"]
    parents = merge_commit.get("parents", {}).get("nodes", [])
    if not parents:
        return None
    pre_merge_sha: str = parents[0]["oid"]

    # Parse changed file paths (patches come from REST later)
    files_nodes = node.get("files", {}).get("nodes", [])
    changed_files: list[tuple[str, str]] = []
    for f in files_nodes:
        path = f.get("path", "")
        if path:
            changed_files.append((path, ""))  # patch filled later

    if not changed_files:
        return None

    # Parse human review comments (line-level only)
    human_comments: list[HumanComment] = []
    reviews_nodes = node.get("reviews", {}).get("nodes", [])
    for review in reviews_nodes:
        comment_nodes = review.get("comments", {}).get("nodes", [])
        for comment in comment_nodes:
            body = comment.get("body", "").strip()
            path = comment.get("path", "")
            line = comment.get("originalLine")
            if body and path and line and isinstance(line, int) and line > 0:
                human_comments.append(
                    HumanComment(body=body, file_path=path, line=line)
                )

    # Filter: only PRs with at least 1 line-level review comment
    if not human_comments:
        return None

    return HistoricalPR(
        number=node["number"],
        title=node.get("title", ""),
        merge_commit_sha=merge_sha,
        pre_merge_sha=pre_merge_sha,
        changed_files=changed_files,
        human_comments=human_comments,
    )


async def _fetch_pr_patches(
    client: httpx.AsyncClient,
    repo_full_name: str,
    pr_number: int,
    headers: dict[str, str],
) -> dict[str, str]:
    """Fetch file patches for a PR via the REST API.

    Args:
        client: Reusable httpx client.
        repo_full_name: Owner/repo string.
        pr_number: Pull request number.
        headers: Auth headers.

    Returns:
        Dict mapping file path to patch string.
    """
    url = f"{REST_API_BASE}/repos/{repo_full_name}/pulls/{pr_number}/files"
    try:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        files_data: list[dict[str, str]] = response.json()
        return {
            f.get("filename", ""): f.get("patch", "")
            for f in files_data
            if f.get("filename")
        }
    except httpx.HTTPError as e:
        logger.warning(
            "Failed to fetch patches for PR #%d: %s", pr_number, e,
        )
        return {}


async def fetch_merged_prs(
    repo_full_name: str,
    pat_token: str,
    limit: int = 20,
) -> list[HistoricalPR]:
    """Fetch merged PRs with line-level review comments from a GitHub repo.

    Uses the GraphQL API for efficient batched fetching.  Only PRs with at
    least one line-level human review comment are returned.

    Args:
        repo_full_name: Owner/repo string (e.g. "encode/starlette").
        pat_token: GitHub personal access token with public_repo scope.
        limit: Maximum number of usable PRs to return.

    Returns:
        List of HistoricalPR objects, up to ``limit``.
    """
    owner, name = repo_full_name.split("/", 1)
    collected: list[HistoricalPR] = []
    cursor: str | None = None
    # Fetch more than needed per page since many PRs will be filtered out
    page_size = min(limit * 3, 100)

    headers = {
        "Authorization": f"Bearer {pat_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        while len(collected) < limit:
            variables: dict[str, str | int | None] = {
                "owner": owner,
                "name": name,
                "limit": page_size,
                "cursor": cursor,
            }

            response = await client.post(
                GRAPHQL_ENDPOINT,
                json={"query": _MERGED_PRS_QUERY, "variables": variables},
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            if "errors" in data:
                error_msg = data["errors"][0].get(
                    "message", "Unknown GraphQL error",
                )
                logger.error("GraphQL error: %s", error_msg)
                raise RuntimeError(f"GraphQL query failed: {error_msg}")

            repo_data = data.get("data", {}).get("repository", {})
            pr_data = repo_data.get("pullRequests", {})
            nodes = pr_data.get("nodes", [])

            if not nodes:
                logger.info("No more PRs to fetch from %s", repo_full_name)
                break

            for node in nodes:
                parsed = _parse_pr_node(node)
                if parsed is not None:
                    collected.append(parsed)
                    if len(collected) >= limit:
                        break

            page_info = pr_data.get("pageInfo", {})
            if page_info.get("hasPreviousPage") and len(collected) < limit:
                cursor = page_info.get("startCursor")
            else:
                break

        # Hydrate patches via REST (GraphQL doesn't expose them)
        rest_headers = {
            "Authorization": f"Bearer {pat_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        for pr in collected:
            patches = await _fetch_pr_patches(
                client, repo_full_name, pr.number, rest_headers,
            )
            pr.changed_files = [
                (path, patches.get(path, ""))
                for path, _ in pr.changed_files
            ]

    logger.info(
        "Fetched %d usable merged PRs from %s (with review comments)",
        len(collected),
        repo_full_name,
    )
    return collected
