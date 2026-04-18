import { helper } from './utils.js';

class Greeter {
    constructor(name) {
        this.name = name;
    }
}

function simpleGreet(name) {
    return 'Hello ' + name;
}

const complexGreet = (names) => {
    let result = '';
    for (let i = 0; i < names.length; i++) {
        if (names[i] === 'Alice') {
            result += 'Hi Alice! ';
        } else if (names[i] === 'Bob') {
            result += 'Hi Bob! ';
        } else {
            result += `Hello ${names[i]}. `;
        }
    }
    while (result.length > 100) {
        result = result.slice(0, 50);
    }
    return result;
};
