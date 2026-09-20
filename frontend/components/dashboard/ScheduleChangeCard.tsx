"use client";

import { useState } from "react";
import { History, RefreshCw } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { ReasonList } from "@/components/explain/ReasonList";
import { useScheduleChangeExplanation } from "@/hooks/useExplain";
import { friendlyApiError } from "@/lib/format";

/** "Why did my schedule change?" — explains the most recent replan, and
 * can trigger one so the explanation is visible without waiting for the
 * nightly job. */
export function ScheduleChangeCard() {
  const { explanation, isLoading, error, refresh, replan } = useScheduleChangeExplanation();
  const [replanning, setReplanning] = useState(false);

  const handleReplan = async () => {
    setReplanning(true);
    await replan();
    setReplanning(false);
  };

  const replanButton = (
    <Button size="sm" variant="secondary" loading={replanning} onClick={handleReplan}>
      {!replanning && <RefreshCw size={13} />}
      Replan now
    </Button>
  );

  return (
    <Card>
      <CardHeader
        eyebrow="Replanning"
        title="Why did my schedule change?"
        action={explanation ? replanButton : undefined}
      />
      {isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : error ? (
        <ErrorState
          message={friendlyApiError(error, "Couldn't load the last replan.")}
          onRetry={() => refresh()}
        />
      ) : !explanation ? (
        <EmptyState
          icon={<History size={20} />}
          title="No replan yet"
          description="Once the schedule is repacked — nightly, or on demand — the reasons show up here."
          action={replanButton}
        />
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-[13px] text-ink">{explanation.summary}</p>
          <ReasonList reasons={explanation.reasons} />
          <p className="tnum text-[11px] text-ink-faint">Replanned on {explanation.occurred_on}</p>
        </div>
      )}
    </Card>
  );
}
