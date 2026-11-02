import { useState } from "react";
import { Download } from "lucide-react";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { installApp, useInstallStatus } from "./install";

export function InstallCard() {
  const status = useInstallStatus();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  return <Card>
    <CardHeader title="Install JobWeaver" description="Open JobWeaver from your Dock or home screen in its own window." />
    <CardBody className="space-y-3 text-sm">
      {status === "installed" ? <p>JobWeaver is installed on this device.</p> : status === "ready" ?
        <Button loading={busy} onClick={() => {
          setBusy(true); setMessage("");
          void installApp().then(outcome => setMessage(outcome === "accepted" ? "Installation accepted. Your browser will finish installing JobWeaver." : "You can install later from your browser’s menu.")).catch(() => setMessage("Installation could not open. Try your browser’s install menu.")).finally(() => setBusy(false));
        }}><Download className="size-4" aria-hidden />Install app</Button> :
        <p>Use your browser’s menu to install JobWeaver. In Brave or Chrome, look for Install JobWeaver or Install page as app. On iPhone or iPad, use Safari → Share → Add to Home Screen. On Mac Safari, use File → Add to Dock.</p>}
      {message && <p role="status">{message}</p>}
      <p className="text-slate-600 dark:text-slate-400">An internet connection is required. To fill employer forms, keep using the browser extension in Brave or Chrome.</p>
    </CardBody>
  </Card>;
}
