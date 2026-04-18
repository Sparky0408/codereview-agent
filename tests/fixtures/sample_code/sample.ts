import { TypeA } from './types';

interface User {
    id: number;
    name: string;
}

class UserManager {
    private users: User[] = [];
}

export function processUser(user: User, force: boolean = false): void {
    if (!user) {
        return;
    }
}

const complexProcess = (users: User[]): number => {
    let count = 0;
    for (const u of users) {
        if (u.id > 0 && u.name) {
            count++;
        } else if (u.id === 0 || !u.name) {
            count--;
        }
    }
    return count;
};
