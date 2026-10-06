import { Compass } from "lucide-react";
import { Link } from "react-router-dom";

import { buttonClasses } from "@/components/ui/button-classes";
import { EmptyState } from "@/components/ui/empty-state";

export function NotFoundPage() {
  return (
    <EmptyState
      icon={Compass}
      title="This page does not exist"
      action={
        <Link to="/" className={buttonClasses()}>
          Go to your Feed
        </Link>
      }
    />
  );
}
