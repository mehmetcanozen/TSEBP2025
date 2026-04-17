interface SignalMeterProps {
  title: string;
  waveform: number[];
  rms: number;
  peak: number;
  accentClass: string;
}

const SignalMeter = ({ title, waveform, rms, peak, accentClass }: SignalMeterProps) => {
  const samples = waveform.length > 0 ? waveform : Array(32).fill(0.08);

  return (
    <div className="rounded-2xl border border-border bg-card/70 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-mono uppercase tracking-[0.22em] text-muted-foreground">
            {title}
          </div>
          <div className="mt-1 text-sm font-semibold text-foreground">
            RMS {(rms * 100).toFixed(1)}%
          </div>
        </div>
        <div className="text-right text-[10px] font-mono uppercase tracking-[0.16em] text-muted-foreground">
          <div>Peak {(peak * 100).toFixed(1)}%</div>
          <div>{samples.length} bins</div>
        </div>
      </div>

      <div className="flex h-24 items-end gap-[3px] overflow-hidden rounded-xl border border-border/60 bg-muted/35 px-3 py-3">
        {samples.map((value, index) => (
          <div
            key={`${title}-${index}`}
            className={`flex-1 rounded-full ${accentClass}`}
            style={{ height: `${Math.max(6, Math.min(100, value * 100))}%` }}
          />
        ))}
      </div>
    </div>
  );
};

export default SignalMeter;
