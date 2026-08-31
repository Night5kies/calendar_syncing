import Link from 'next/link';

import { HeroSlots } from '../components/HeroSlots';
import { RecentRequests } from '../components/RecentRequests';

export default function HomePage() {
  return (
    <main className="wrap page">
      <section className="hero-grid">
        <div className="stack-loose reveal" style={{ ['--i' as string]: 0 }}>
          <h1 className="title-hero">
            <span>Pick a time</span> <span>before the thread</span> <span>dies.</span>
          </h1>
          <p className="lede">
            Send one link to the group chat. Everyone taps a time in their browser — no account, no
            app. You confirm the winner and it lands on their calendars.
          </p>
          <div className="row">
            <Link className="btn" href="/create">
              Create a request
            </Link>
            <a className="btn btn-quiet" href="#how">
              How it works
            </a>
          </div>
        </div>

        <div className="reveal" style={{ ['--i' as string]: 1 }}>
          <HeroSlots />
        </div>
      </section>

      <hr className="hairline" />

      <section className="stack-loose" id="how">
        <h2 className="title-page">Three moves, one booked plan.</h2>
        <ol className="steps">
          <li className="step">
            <h3>Propose</h3>
            <p>
              Start from a shape — meal, coffee, study, hangout — and put up to five times on the
              table. Or let SYZY read your calendar and pick the openings for you.
            </p>
          </li>
          <li className="step">
            <h3>Share</h3>
            <p>
              Paste the link in the chat. Everyone gets their own private link too, so a nudge goes
              straight to the person who hasn’t answered.
            </p>
          </li>
          <li className="step">
            <h3>Confirm</h3>
            <p>
              Watch the votes land, pick the winner, and SYZY writes it to your Google Calendar and
              sends everyone an invite they can save.
            </p>
          </li>
        </ol>
      </section>

      <RecentRequests />

      <hr className="hairline" />

      <section className="pair">
        <div className="stack-tight">
          <p className="label">Guests stay guests</p>
          <p className="muted">
            Attendees never make an account. They are recognized by the link they were sent, and can
            change their answer any time from the same link.
          </p>
        </div>
        <div className="stack-tight">
          <p className="label">Calendars stay private</p>
          <p className="muted">
            When you connect Google Calendar, SYZY reads free and busy time only. Event titles,
            guests, and notes are never fetched.
          </p>
        </div>
      </section>
    </main>
  );
}
