import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Card } from "@/components/ui/card";
import { LoadingMark } from "@/components/ui/spinner";

export function GenerationProgress({ progress, jobId }: { progress: string; jobId: string }) {
  const [opened] = useState(() => Date.now());
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - opened) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [opened]);
  return <Card className="space-y-4 p-6">
    <div className="flex items-center gap-3"><LoadingMark compact /><h1 className="text-xl font-semibold">Preparing your Draft</h1></div>
    <p role="status" aria-live="polite">{progress || "Waiting to start"}</p>
    <p className="text-sm text-slate-600 dark:text-slate-400">Waiting here: {Math.floor(elapsed / 60)}m {elapsed % 60}s. Generation continues if you leave this page.</p>
    <p className="text-sm">Your Draft is ready only after its Facts and Tailoring Trace have been checked.</p>
    <Link className="inline-block text-sm underline" to={`/jobs/${jobId}`}>Back to Job</Link>
  </Card>;
}
