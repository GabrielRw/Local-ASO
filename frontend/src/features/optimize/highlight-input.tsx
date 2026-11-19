import { useRef } from "react";
import { FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { toneMark, type Segment } from "./highlight";

/** "12/30" next to a field label; turns red past Apple's limit. */
export function CharCount({ value, max, id }: { value: string; max: number; id?: string }) {
  return (
    <span
      id={id}
      className={cn("text-muted-foreground ml-auto text-xs font-normal tabular-nums", value.length > max && "text-destructive")}
    >
      {value.length}/{max}
    </span>
  );
}

/**
 * A text input whose words are tinted by a mirror layer drawn behind it. The
 * input keeps its own caret, selection, and accessibility; only its glyphs are
 * transparent so the mirror shows through. Scroll position is kept in sync.
 */
export function HighlightInput({
  id,
  label,
  value,
  max,
  segments,
  onChange,
  placeholder,
  required,
  describedBy,
}: {
  id: string;
  label: string;
  value: string;
  max: number;
  segments: Segment[];
  onChange: (value: string) => void;
  placeholder?: string;
  required?: boolean;
  describedBy?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const mirrorRef = useRef<HTMLDivElement>(null);
  const sync = () =>
    window.requestAnimationFrame(() => {
      if (mirrorRef.current && inputRef.current) mirrorRef.current.scrollLeft = inputRef.current.scrollLeft;
    });

  return (
    <>
      <FieldLabel htmlFor={id} className="flex w-full items-baseline">
        {label}
        <CharCount value={value} max={max} />
      </FieldLabel>
      <div className="dark:bg-input/30 relative rounded-lg">
        <div
          ref={mirrorRef}
          aria-hidden
          className="pointer-events-none absolute inset-0 flex items-center overflow-hidden rounded-lg border border-transparent px-2.5 py-1 text-base md:text-sm"
        >
          <span className="whitespace-pre">
            {segments.map((segment, index) =>
              segment.tone ? (
                <mark key={index} className={cn("rounded-[3px]", toneMark[segment.tone])}>
                  {segment.text}
                </mark>
              ) : (
                <span key={index}>{segment.text}</span>
              ),
            )}
          </span>
        </div>
        <Input
          ref={inputRef}
          id={id}
          value={value}
          maxLength={max}
          required={required}
          placeholder={placeholder}
          aria-describedby={describedBy}
          spellCheck={false}
          autoComplete="off"
          onChange={(event) => {
            onChange(event.target.value);
            sync();
          }}
          onScroll={sync}
          onKeyUp={sync}
          onClick={sync}
          onSelect={sync}
          onFocus={sync}
          className="caret-foreground selection:bg-primary/25 relative bg-transparent text-transparent selection:text-transparent dark:bg-transparent"
        />
      </div>
    </>
  );
}
