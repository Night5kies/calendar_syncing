'use client';

import { useEffect, useState } from 'react';

import { Slot, Tally, type SlotState } from './Slot';
import { browserTimezone } from '../lib/time';

type Demo = {
  startIso: string;
  endIso: string;
  picked: number;
  maybe: number;
};

function upcoming(
  offsetDays: number,
  hour: number,
  minute: number,
  lengthMin: number,
): [string, string] {
  const start = new Date();
  start.setDate(start.getDate() + offsetDays);
  start.setHours(hour, minute, 0, 0);
  const end = new Date(start.getTime() + lengthMin * 60_000);
  return [start.toISOString(), end.toISOString()];
}

// Four people, one answer each: three picked a time, one is still a maybe.
function buildDemo(): Demo[] {
  const rows: Array<[number, number, number, number, number, number]> = [
    // offsetDays, hour, minute, lengthMin, picked, maybe
    [3, 19, 0, 75, 3, 0],
    [5, 12, 30, 75, 0, 1],
    [6, 18, 30, 75, 0, 0],
  ];
  return rows.map(([offset, hour, minute, length, picked, maybe]) => {
    const [startIso, endIso] = upcoming(offset, hour, minute, length);
    return { startIso, endIso, picked, maybe };
  });
}

/**
 * The hero is the product in one gesture: three candidate times in play,
 * then one going solid. Everything else on this page explains that.
 */
export function HeroSlots() {
  const [demo, setDemo] = useState<Demo[] | null>(null);
  const [settled, setSettled] = useState(false);
  const timezone = browserTimezone();

  useEffect(() => {
    setDemo(buildDemo());

    const reduced =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (reduced) {
      setSettled(true);
      return;
    }
    const timer = window.setTimeout(() => setSettled(true), 2200);
    return () => window.clearTimeout(timer);
  }, []);

  if (!demo) {
    return (
      <div className="stack-tight" aria-hidden="true">
        <div className="skel" style={{ height: '5.75rem' }} />
        <div className="skel" style={{ height: '5.75rem' }} />
        <div className="skel" style={{ height: '5.75rem' }} />
      </div>
    );
  }

  const total = 4;

  return (
    <div className="stack-tight">
      {demo.map((option, index) => {
        const isWinner = index === 0;
        const state: SlotState = settled ? (isWinner ? 'won' : 'lost') : 'open';
        return (
          <Slot
            key={option.startIso}
            startIso={option.startIso}
            endIso={option.endIso}
            timezone={timezone}
            index={index + 1}
            state={state}
          >
            {settled && isWinner ? (
              <p className="tally">Booked · everyone got the invite</p>
            ) : (
              <Tally picked={option.picked} maybe={option.maybe} declined={0} total={total} />
            )}
          </Slot>
        );
      })}
      <p className="muted" aria-live="polite">
        {settled
          ? 'One tap to confirm, and the thread can move on.'
          : 'Four people, three options, one tap each.'}
      </p>
    </div>
  );
}
