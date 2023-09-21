function encodeEmail(text) {
    var result = [];
    for (var i = 0; i < text.length; i++) {
        if (i % 2 === 0) {
            result[i] = text.charCodeAt(i) + 0x66ccff;
        } else {
            result[i] = text.charCodeAt(i) - 0xee0000;
        }
    }
    return result.join(".");
}

function decodeEmail(data) {
    var numbers = data.split(".");
    var result = "";
    for (var i = 0; i < numbers.length; i++) {
        if (i % 2 === 0) {
            result += String.fromCharCode(parseInt(numbers[i]) - 0x66ccff);
        } else {
            result += String.fromCharCode(parseInt(numbers[i]) + 0xee0000);
        }
    }
    return result;
}
