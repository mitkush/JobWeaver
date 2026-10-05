import { Download, Trash2 } from "lucide-react";
import { useState } from "react";

import { api, unwrap } from "@/api/client";
import { useDeleteFactBank, useDocuments, useFacts } from "@/api/hooks";
import { PageHeader } from "@/app/AppShell";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { PageSpinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast-context";
import { DocumentUploader } from "@/features/fact-bank/DocumentUploader";
import { FactBankEditor } from "@/features/fact-bank/FactBankEditor";

async function downloadExport() {
  const data = await unwrap(api.GET("/api/fact-bank/export"));
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "jobweaver-fact-bank.json";
  link.click();
  URL.revokeObjectURL(url);
}

export function FactBankPage() {
  const facts = useFacts();
  const documents = useDocuments();
  const remove = useDeleteFactBank();
  const [confirm, setConfirm] = useState(false);
  const toast = useToast();

  if (facts.isPending || documents.isPending) return <PageSpinner />;
  if (facts.isError) return <Alert tone="error">{facts.error.message}</Alert>;

  return (
    <>
      <PageHeader
        title="Fact Bank"
        description="Everything tailored applications may say about you. Nothing outside this list is ever used."
        action={
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={() => downloadExport().catch((e: Error) => toast("error", e.message))}
            >
              <Download className="size-4" aria-hidden />
              Export
            </Button>
            <Button variant="ghost" onClick={() => setConfirm(true)}>
              <Trash2 className="size-4" aria-hidden />
              Delete all
            </Button>
          </div>
        }
      />
      <div className="space-y-8">
        <Card>
          <CardHeader
            title="Documents"
            description="Replacing a document rebuilds the Fact Bank. Facts you edited or added yourself are always kept."
          />
          <CardBody>
            <DocumentUploader documents={documents.data ?? []} />
          </CardBody>
        </Card>
        <FactBankEditor facts={facts.data} />
      </div>
      <ConfirmDialog
        open={confirm}
        title="Delete your documents and Fact Bank?"
        confirmLabel="Delete everything"
        loading={remove.isPending}
        onCancel={() => setConfirm(false)}
        onConfirm={async () => {
          await remove.mutateAsync();
          setConfirm(false);
          toast("success", "Documents and Fact Bank deleted");
        }}
      >
        This removes all {facts.data.length} Facts and your uploaded documents. You will need to upload
        your resume again before JobWeaver can tailor applications.
      </ConfirmDialog>
    </>
  );
}
