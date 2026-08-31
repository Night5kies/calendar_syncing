import type { ReactNode } from 'react';

import { shapeSlot } from '../lib/time';

export type SlotState = 'open' | 'picked' | 'won' | 'lost';

type BaseProps = {
  startIso: string;
  endIso: string;
  timezone: string;
  /** Shared vocabulary between organizer and group chat: "Option 2". */
  index?: number;
  state?: SlotState;
  /** Anything below the rail: a tally, a reason, an action. */
  children?: ReactNode;
  note?: ReactNode;
};

function SlotFace({ startIso, endIso, timezone, index, note, children }: BaseProps) {
  const shape = shapeSlot(startIso, endIso, timezone);

  return (
    <>
      <div className="slot-date" aria-hidden="true">
        <span className="slot-dow">{shape.weekday}</span>
        <span className="slot-day">{shape.day}</span>
      </div>
      <div className="slot-body">
        <div className="slot-meta">
          <span className="slot-time">{shape.time}</span>
          {typeof index === 'number' ? <span className="slot-mark">Option {index}</span> : null}
        </div>
        <div className="track" aria-hidden="true">
          <span
            className="track-fill"
            style={{ ['--from' as string]: `${shape.from}%`, ['--span' as string]: `${shape.span}%` }}
          />
        </div>
        {note ? <p className="slot-note">{note}</p> : null}
        {children}
      </div>
    </>
  );
}

/** Read-only slot. */
export function Slot(props: BaseProps) {
  const shape = shapeSlot(props.startIso, props.endIso, props.timezone);
  return (
    <div className="slot" data-state={props.state ?? 'open'}>
      <span className="sr-only">{shape.full}</span>
      <SlotFace {...props} />
    </div>
  );
}

/** Tappable slot — the attendee's pick, and the organizer's shortlist. */
export function SlotChoice({
  onSelect,
  selected,
  ...props
}: BaseProps & { onSelect: () => void; selected: boolean }) {
  const shape = shapeSlot(props.startIso, props.endIso, props.timezone);
  return (
    <button
      type="button"
      className="slot"
      data-state={props.state ?? (selected ? 'picked' : 'open')}
      aria-pressed={selected}
      onClick={onSelect}
    >
      <span className="sr-only">{shape.full}</span>
      <SlotFace {...props} />
    </button>
  );
}

/**
 * Who wants this time, as one mark per person. Dots beat a proportional bar
 * here: the groups are small, and a dot per person is countable at a glance
 * without competing with the day rail directly above it.
 */
export function Tally({
  picked,
  maybe,
  declined,
  total,
}: {
  picked: number;
  maybe: number;
  declined: number;
  total: number;
}) {
  const answered = picked + maybe + declined;
  const pending = Math.max(0, total - answered);

  const words =
    answered === 0
      ? 'Nobody yet'
      : [
          picked > 0 ? `${picked} in` : null,
          maybe > 0 ? `${maybe} maybe` : null,
          declined > 0 ? `${declined} out` : null,
        ]
          .filter(Boolean)
          .join(' · ');

  if (total > 10) {
    return <p className="tally">{words}</p>;
  }

  const marks: Array<'picked' | 'maybe' | 'declined' | 'pending'> = [
    ...Array<'picked'>(picked).fill('picked'),
    ...Array<'maybe'>(maybe).fill('maybe'),
    ...Array<'declined'>(declined).fill('declined'),
    ...Array<'pending'>(pending).fill('pending'),
  ];

  return (
    <p className="tally">
      <span className="tally-marks" aria-hidden="true">
        {marks.map((mark, index) => (
          <span className="tally-mark" data-kind={mark} key={index} />
        ))}
      </span>
      <span>{words}</span>
    </p>
  );
}
