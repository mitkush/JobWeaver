type Status = { connected: false; error?: string } | { connected: true; email: string; expiresAt: string };

const statusText = document.querySelector<HTMLParagraphElement>("#status")!;
const connectButton = document.querySelector<HTMLButtonElement>("#connect")!;
const disconnectButton = document.querySelector<HTMLButtonElement>("#disconnect")!;

function ask(type: "status" | "connect" | "disconnect"): Promise<Status> {
  return chrome.runtime.sendMessage({ type });
}

function show(status: Status) {
  connectButton.hidden = status.connected;
  disconnectButton.hidden = !status.connected;
  statusText.textContent = status.connected
    ? `Connected as ${status.email}.`
    : (status.error ?? "Not connected. Connect to use your JobWeaver Drafts here.");
}

connectButton.addEventListener("click", async () => {
  connectButton.disabled = true;
  await ask("connect");
  window.close();
});

disconnectButton.addEventListener("click", async () => {
  disconnectButton.disabled = true;
  show(await ask("disconnect"));
  disconnectButton.disabled = false;
});

void ask("status").then(show);
