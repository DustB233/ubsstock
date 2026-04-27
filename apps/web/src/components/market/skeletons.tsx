function SkeletonLine({ className }: { className: string }) {
  return <div className={`animate-pulse rounded-full bg-white/10 ${className}`} />;
}

function SkeletonPanel({
  className = "",
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={`rounded-[1.8rem] border border-white/8 bg-slate-950/40 p-6 shadow-[0_20px_60px_rgba(3,7,18,0.22)] ${className}`}
    >
      {children}
    </div>
  );
}

export function StockDetailPageSkeleton() {
  return (
    <div className="space-y-6">
      <SkeletonPanel className="p-8">
        <SkeletonLine className="h-3 w-36" />
        <SkeletonLine className="mt-4 h-12 w-72" />
        <SkeletonLine className="mt-4 h-4 w-full max-w-3xl" />
        <div className="mt-8 grid gap-4 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <SkeletonLine key={index} className="h-28 w-full rounded-[1.4rem]" />
          ))}
        </div>
      </SkeletonPanel>
      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <SkeletonPanel>
          <SkeletonLine className="h-4 w-40" />
          <SkeletonLine className="mt-6 h-[320px] w-full rounded-[1.6rem]" />
        </SkeletonPanel>
        <SkeletonPanel>
          <SkeletonLine className="h-4 w-44" />
          <SkeletonLine className="mt-6 h-4 w-full" />
          <SkeletonLine className="mt-3 h-4 w-full" />
          <SkeletonLine className="mt-3 h-4 w-11/12" />
          <SkeletonLine className="mt-8 h-36 w-full rounded-[1.5rem]" />
        </SkeletonPanel>
      </div>
    </div>
  );
}

export function ComparisonPageSkeleton() {
  return (
    <div className="space-y-6">
      <SkeletonPanel className="p-8">
        <SkeletonLine className="h-3 w-40" />
        <SkeletonLine className="mt-4 h-12 w-80" />
        <SkeletonLine className="mt-4 h-4 w-full max-w-3xl" />
        <div className="mt-8 flex flex-wrap gap-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <SkeletonLine key={index} className="h-11 w-32 rounded-full" />
          ))}
        </div>
      </SkeletonPanel>
      <div className="grid gap-6 xl:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <SkeletonPanel key={index}>
            <SkeletonLine className="h-4 w-28" />
            <SkeletonLine className="mt-5 h-8 w-40" />
            <SkeletonLine className="mt-4 h-4 w-32" />
          </SkeletonPanel>
        ))}
      </div>
      <SkeletonPanel>
        <SkeletonLine className="h-4 w-52" />
        <SkeletonLine className="mt-6 h-72 w-full rounded-[1.6rem]" />
      </SkeletonPanel>
    </div>
  );
}

