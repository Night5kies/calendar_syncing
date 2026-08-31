import Link from 'next/link';

export default function HomePage() {
  return (
    <main className="shell">
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">SYZY - Next.js-first</p>
          <h1>Use chat for discussion. Use SYZY for decision and follow-through.</h1>
          <p className="lede">
            A mobile-web scheduling flow for meals, coffee, hangouts, and small group plans. No
            app install required for guests.
          </p>
          <div className="hero-actions">
            <Link className="button button-primary" href="/create">
              Create a request
            </Link>
            <Link className="button button-secondary" href="/create">
              Start web prototype
            </Link>
          </div>
        </div>
        <div className="hero-card">
          <div className="stat-row">
            <span>Entry point</span>
            <strong>Shared link in a group chat</strong>
          </div>
          <div className="stat-row">
            <span>Organizer goal</span>
            <strong>Get from "maybe" to booked</strong>
          </div>
          <div className="stat-row">
            <span>Attendee friction</span>
            <strong>No account required</strong>
          </div>
          <div className="stat-row">
            <span>Core MVP</span>
            <strong>Manual poll + response link + reminders + confirmation artifact</strong>
          </div>
        </div>
      </section>

      <section className="grid-two">
        <article className="panel">
          <p className="section-label">Why web first</p>
          <h2>Less friction at the exact moment people are asked to respond.</h2>
          <p>
            The first interaction is usually a text message, not an app store search. A Next.js-first
            launch keeps the invite flow native to how people already coordinate.
          </p>
        </article>
        <article className="panel">
          <p className="section-label">What this version covers</p>
          <ul className="flat-list">
            <li>Create a request with 3-5 manual options</li>
            <li>View organizer request details</li>
            <li>Open an attendee response page from a link</li>
            <li>Ping non-responders</li>
            <li>Confirm a winning option and download an ICS artifact</li>
          </ul>
        </article>
      </section>
    </main>
  );
}
