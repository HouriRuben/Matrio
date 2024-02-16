var socket = new WebSocket("ws://localhost:8765");

socket.onmessage = function (event) {
    var message = event.data;
    if (message === "reload") {
        setTimeout(function () {
            location.reload();
        }, 1000);
    }
};

socket.onerror = function (error) {
    console.log(`WebSocket error: ${error}`);
};

socket.onopen = function (event) {
    console.log("WebSocket is open now.");
};

socket.onclose = function (event) {
    console.log("WebSocket is closed now.");
};