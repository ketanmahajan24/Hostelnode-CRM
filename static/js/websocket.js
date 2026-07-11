(function () {
  let socket;
  let reconnectDelay = 1000;

  function connect() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${protocol}//${window.location.host}/ws`);

    socket.onopen = () => {
      reconnectDelay = 1000;
      console.log("[ws] connected");
    };

    socket.onmessage = (event) => {
      try {
        const { event: type, data } = JSON.parse(event.data);
        handleEvent(type, data);
      } catch (err) {
        console.error("[ws] bad payload", err);
      }
    };

    socket.onclose = () => {
      setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 1.5, 15000);
    };

    socket.onerror = () => socket.close();
  }

  function handleEvent(type, data) {
    if (type === "new_message") {
      const activeWaId = document.getElementById("chat-window-inner")?.dataset.waId;
      const incomingWaId = data.message?.wa_id;

      // Refresh chat list sidebar so previews / unread badges update
      const chatListBody = document.getElementById("chat-list-body");
      if (chatListBody && window.htmx) {
        htmx.ajax("GET", "/conversations/list", { target: "#chat-list-body", swap: "innerHTML" });
      }

      // If the affected chat is currently open, refresh the message thread
      if (activeWaId && activeWaId === incomingWaId && window.htmx) {
        htmx.ajax("GET", `/conversations/${incomingWaId}/window`, {
          target: "#chat-window-inner", swap: "outerHTML",
        });
      }

      // Desktop notification for inbound messages when the tab isn't focused
      if (data.message?.direction === "inbound" && document.hidden) {
        notify(data.contact?.name || incomingWaId, previewText(data.message));
      }
    }

    if (type === "status_update") {
      // Cheapest correct approach: re-render the open thread so ticks refresh
      const activeWaId = document.getElementById("chat-window-inner")?.dataset.waId;
      if (activeWaId && window.htmx) {
        htmx.ajax("GET", `/conversations/${activeWaId}/window`, {
          target: "#chat-window-inner", swap: "outerHTML",
        });
      }
    }
  }

  function previewText(message) {
    if (message.type === "text") return message.text;
    return `[${message.type}]`;
  }

  function notify(title, body) {
    if (!("Notification" in window)) return;
    if (Notification.permission === "granted") {
      new Notification(title, { body });
    } else if (Notification.permission !== "denied") {
      Notification.requestPermission().then((perm) => {
        if (perm === "granted") new Notification(title, { body });
      });
    }
  }

  connect();
})();
