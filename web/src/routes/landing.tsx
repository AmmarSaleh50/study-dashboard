import { useCallback, useEffect, useRef, useState } from "react";
import { Navigate } from "react-router-dom";
import { Wordmark } from "@/components/brand/wordmark";
import { useSession } from "@/lib/queries";
import { useDocumentTitle, useHtmlLang } from "@/lib/document-head";
import "@/styles/landing.css";

const GH_REPO = "openstudy-dev/OpenStudy";
const GH_URL = `https://github.com/${GH_REPO}`;
const INSTALL_URL = `${GH_URL}/blob/main/INSTALL.md`;

const THEMES = [
  { src: "/screenshots/theme-zine.png", name: "Zine" },
  { src: "/screenshots/theme-library.png", name: "Library" },
  { src: "/screenshots/theme-swiss.png", name: "Swiss" },
  { src: "/screenshots/theme-terminal.gif", name: "Terminal" },
  { src: "/screenshots/theme-classic.png", name: "Classic" },
] as const;

function GhPill({ stars }: { stars: number | null }) {
  return (
    <a
      className="gh"
      href={GH_URL}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`OpenStudy on GitHub${stars !== null ? ` — ${stars} stars` : ""}`}
    >
      <svg className="gh-icon" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" clipRule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z" /></svg>
      <svg className="gh-star" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.75.75 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z" /></svg>
      <span className="gh-count">{stars ?? "—"}</span>
    </a>
  );
}

function GhCta({ label, stars }: { label: string; stars: number | null }) {
  return (
    <a className="cta-primary" href={GH_URL} target="_blank" rel="noopener noreferrer">
      <svg className="cta-gh-icon" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" clipRule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z" /></svg>
      <span>{label}</span>
      {stars !== null && (
        <span className="cta-stars" aria-label={`${stars} stars`}>
          <svg className="cta-star" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
            <path d="M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.75.75 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z" />
          </svg>
          {stars}
        </span>
      )}
      <span className="cta-arrow" aria-hidden="true">→</span>
    </a>
  );
}

function ThemeCarousel() {
  const [idx, setIdx] = useState(0);
  const [paused, setPaused] = useState(false);
  const resumeTimer = useRef<number | null>(null);

  useEffect(() => {
    if (paused) return;
    const t = window.setInterval(() => setIdx((i) => (i + 1) % THEMES.length), 4500);
    return () => window.clearInterval(t);
  }, [paused]);

  const pauseThenResume = useCallback(() => {
    setPaused(true);
    if (resumeTimer.current) window.clearTimeout(resumeTimer.current);
    resumeTimer.current = window.setTimeout(() => setPaused(false), 9000);
  }, []);

  const go = useCallback(
    (delta: number) => {
      setIdx((i) => (i + delta + THEMES.length) % THEMES.length);
      pauseThenResume();
    },
    [pauseThenResume],
  );

  const jump = useCallback(
    (target: number) => {
      setIdx(target);
      pauseThenResume();
    },
    [pauseThenResume],
  );

  return (
    <div
      className="hero-themes"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      {THEMES.map((t, i) => (
        <img
          key={t.src}
          className={`hero-theme-img${i === idx ? " is-active" : ""}`}
          src={t.src}
          alt={`${t.name} theme`}
          loading={i === 0 ? "eager" : "lazy"}
          draggable={false}
        />
      ))}

      <button
        type="button"
        className="hero-theme-nav hero-theme-nav-prev"
        onClick={() => go(-1)}
        aria-label="Previous theme"
      >
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M15 6l-6 6 6 6" />
        </svg>
      </button>
      <button
        type="button"
        className="hero-theme-nav hero-theme-nav-next"
        onClick={() => go(1)}
        aria-label="Next theme"
      >
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M9 6l6 6-6 6" />
        </svg>
      </button>

      <div className="hero-theme-dots" role="tablist" aria-label="Theme">
        {THEMES.map((t, i) => (
          <button
            key={t.name}
            type="button"
            role="tab"
            aria-selected={i === idx}
            aria-label={`Show ${t.name} theme`}
            className={`hero-theme-dot${i === idx ? " is-active" : ""}`}
            onClick={() => jump(i)}
          />
        ))}
      </div>

      <span className="hero-theme-name" aria-live="polite">{THEMES[idx].name}</span>
    </div>
  );
}

export default function Landing() {
  useDocumentTitle();
  useHtmlLang();

  const session = useSession();
  const [stars, setStars] = useState<number | null>(null);
  const [navHidden, setNavHidden] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`https://api.github.com/repos/${GH_REPO}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d: { stargazers_count?: number } | null) => {
        if (!cancelled && d && typeof d.stargazers_count === "number") {
          setStars(d.stargazers_count);
        }
      })
      .catch(() => { });
    return () => {
      cancelled = true;
    };
  }, []);

  // Smart hide-on-scroll-down navbar — same pattern Linear / Vercel use.
  useEffect(() => {
    let lastY = window.scrollY;
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(() => {
        const y = window.scrollY;
        const dy = y - lastY;
        if (y < 80) {
          setNavHidden(false);
        } else if (dy > 6) {
          setNavHidden(true);
        } else if (dy < -6) {
          setNavHidden(false);
        }
        lastY = y;
        ticking = false;
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Reveal sections / hero / final / terminal as they scroll into view.
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const obs = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            obs.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" },
    );
    document
      .querySelectorAll(".landing .hero, .landing .sec, .landing .final, .landing .terminal")
      .forEach((el) => obs.observe(el));
    return () => obs.disconnect();
  }, []);

  if (session.data?.authed) {
    return <Navigate to="/app" replace />;
  }

  return (
    <div className="landing">
      <div className="wrap">
        {/* ==================== NAV ==================== */}
        <header className={`landing-nav${navHidden ? " is-hidden" : ""}`} role="banner">
          <nav className="nav">
            <a className="brand" href="/" aria-label="OpenStudy home">
              <Wordmark variant="auto-os" />
            </a>
            <ul>
              <li><a href="#mcp">MCP?</a></li>
              <li><a href="#day0">Day 0</a></li>
              <li><a href="#daily">Day to day</a></li>
              <li><a href="#extend">Extend</a></li>
              <li><a href="#selfhost">Self-host</a></li>
            </ul>
            <GhPill stars={stars} />
          </nav>
        </header>

        {/* ==================== HERO ==================== */}
        <section className="hero container">
          <div className="hero-wordmark">
            <Wordmark variant="auto-os" />
          </div>

          <p className="lead">
            Make your Claude/ChatGPT subscription more powerful for your semester.
          </p>

          <div className="hero-ctas">
            <GhCta label="GitHub" stars={stars} />
            <a className="cta-secondary" href={INSTALL_URL} target="_blank" rel="noopener noreferrer">
              Install guide
            </a>
          </div>

          <div className="hero-screen">
            <div className="mock">
              <div className="chrome">
                <div className="dots"><span /><span /><span /></div>
              </div>
              <ThemeCarousel />
            </div>
          </div>
        </section>

        {/* ==================== MCP PRIMER ==================== */}
        <section className="sec container" id="mcp">
          <div className="sec-label">§ 00 / Background</div>
          <h2 className="sec-h">What's MCP?</h2>

          <div className="mcp-body">
            <p>
              A way for your AI to talk to outside apps. Without MCP, an assistant like Claude or ChatGPT only knows what you paste into the chat. With MCP, it can use other apps — your calendar, your notes, a database, a service in the cloud — wherever they're running.
            </p>
            <p>
              OpenStudy ships an MCP server alongside the dashboard. Connect your AI client to that server and the AI gets read and write access to a structured view of your semester.
            </p>

            <div className="mcp-diagram" aria-hidden="true">
              <div className="mcp-side">
                <div className="mcp-side-h">Your AI app</div>
                <div className="mcp-side-b">Claude.ai · ChatGPT · Claude Code · Codex · anything that speaks MCP</div>
              </div>
              <div className="mcp-arrow">
                <span className="mcp-arrow-label">MCP</span>
                <div className="mcp-arrow-track">
                  <span className="mcp-arrow-dot" />
                </div>
              </div>
              <div className="mcp-side">
                <div className="mcp-side-h">OpenStudy</div>
                <div className="mcp-side-b">Your courses, lectures, deadlines, PDFs · 44 tools the AI can call</div>
              </div>
            </div>
          </div>
        </section>

        {/* ==================== DAY 0 ==================== */}
        <section className="sec container" id="day0">
          <div className="sec-label">§ 01 / Day 0</div>
          <h2 className="sec-h">Hand it the whole semester at once.</h2>

          <div className="demo demo-day0" aria-hidden="true">
            {/* Left pane — Claude Desktop chat */}
            <div className="demo-pane demo-pane-chat">
              <div className="demo-chrome">
                <span className="demo-dot" />
                <span className="demo-dot" />
                <span className="demo-dot" />
                <span className="demo-app">Your AI app</span>
              </div>
              <div className="demo-chat">
                <div className="demo-bubble demo-bubble-you">
                  <span className="demo-bubble-label">You</span>
                  <span className="demo-typewriter">
                    <span className="demo-typewriter-text">Set up my semester from these:</span>
                  </span>
                  <div className="demo-attachments">
                    <span className="demo-attach demo-attach-1">moodle-export.zip</span>
                    <span className="demo-attach demo-attach-2">timetable.pdf</span>
                    <span className="demo-attach demo-attach-3">syllabi/</span>
                    <span className="demo-attach demo-attach-4">exams.csv</span>
                  </div>
                </div>
                <div className="demo-bubble demo-bubble-ai">
                  <span className="demo-bubble-label">Claude</span>
                  <div className="demo-tools">
                    <div className="demo-tool demo-tool-1">
                      <svg className="demo-tool-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
                      </svg>
                      <span className="demo-tool-name">create_course</span>
                      <span className="demo-tool-result">Result</span>
                    </div>
                    <div className="demo-tool demo-tool-2">
                      <svg className="demo-tool-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
                      </svg>
                      <span className="demo-tool-name">create_schedule_slot</span>
                      <span className="demo-tool-result">Result</span>
                    </div>
                    <div className="demo-tool demo-tool-3">
                      <svg className="demo-tool-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
                      </svg>
                      <span className="demo-tool-name">create_lecture</span>
                      <span className="demo-tool-result">Result</span>
                    </div>
                    <div className="demo-tool demo-tool-4">
                      <svg className="demo-tool-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
                      </svg>
                      <span className="demo-tool-name">create_deliverable</span>
                      <span className="demo-tool-result">Result</span>
                    </div>
                    <div className="demo-tool demo-tool-5">
                      <svg className="demo-tool-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
                      </svg>
                      <span className="demo-tool-name">create_exam</span>
                      <span className="demo-tool-result">Result</span>
                    </div>
                    <div className="demo-tool-done">
                      <span className="demo-tool-tick" aria-hidden="true">✓</span>
                      Done.
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Right pane — counts of what got imported */}
            <div className="demo-pane demo-pane-dash">
              <div className="demo-chrome">
                <span className="demo-dot" />
                <span className="demo-dot" />
                <span className="demo-dot" />
                <span className="demo-app">OpenStudy</span>
              </div>
              <div className="demo-stats">
                <div className="demo-stat demo-stat-1">
                  <span className="demo-stat-num">5</span>
                  <span className="demo-stat-label">courses</span>
                </div>
                <div className="demo-stat demo-stat-2">
                  <span className="demo-stat-num">47</span>
                  <span className="demo-stat-label">lectures</span>
                </div>
                <div className="demo-stat demo-stat-3">
                  <span className="demo-stat-num">14</span>
                  <span className="demo-stat-label">deliverables</span>
                </div>
                <div className="demo-stat demo-stat-4">
                  <span className="demo-stat-num">4</span>
                  <span className="demo-stat-label">exams</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ==================== DAY TO DAY ==================== */}
        <section className="sec container" id="daily">
          <div className="sec-label">§ 02 / Day to day</div>
          <h2 className="sec-h">Then just talk.</h2>

          <div className="flows flows-shots">
            <figure className="flow flow-shot">
              <div className="when">After a lecture</div>
              <img
                src="/screenshots/claude-after-lecture.png"
                alt="A Claude Desktop conversation: 'Alright the VL2 is done here at slide 9.' Claude logs the lecture, adds seven study topics, and updates the lecture record through OpenStudy's MCP tools."
                loading="lazy"
              />
            </figure>

            <figure className="flow flow-shot">
              <div className="when">Falling behind</div>
              <img
                src="/screenshots/claude-fall-behind.png"
                alt="A Claude Desktop conversation: 'What am I falling behind in this week?' Claude calls the get_fall_behind tool, marks RA and RN as critical, AML as warn, ASB as ok, and prioritises RA > RN > AML."
                loading="lazy"
              />
            </figure>
          </div>
        </section>

        {/* ==================== EXTEND ==================== */}
        <section className="sec container" id="extend">
          <div className="sec-label">§ 03 / Extend</div>
          <h2 className="sec-h">What I built around mine.</h2>

          <div className="extend-grid">
            <article className="extend-card">
              <h3 className="extend-card-title">LMS auto-sync</h3>
              <figure className="extend-shot">
                <div className="extend-shot-media">
                  <img src="/screenshots/extend-n8n.png" alt="n8n workflow with three triggers feeding a single Moodle sync node." loading="lazy" />
                </div>
                <figcaption>
                  <p>Manual, cron, and webhook triggers — all sync my LMS into OpenStudy storage.</p>
                </figcaption>
              </figure>
            </article>

            <article className="extend-card">
              <h3 className="extend-card-title">Sync reports</h3>
              <figure className="extend-shot">
                <div className="extend-shot-media">
                  <img src="/screenshots/extend-telegram.png" alt="Telegram bot DM showing Moodle sync results." loading="lazy" />
                </div>
                <figcaption>
                  <p>Each sync DMs me what changed</p>
                </figcaption>
              </figure>
            </article>

            <article className="extend-card">
              <h3 className="extend-card-title">Pre-lecture briefs</h3>
              <figure className="extend-shot">
                <div className="extend-shot-media">
                  <img src="/screenshots/extend-prelecture.png" alt="Telegram briefing from the OpenStudy bot — a detailed pre-lecture rundown of what the user has not yet studied vs. what's coming up." loading="lazy" />
                </div>
                <figcaption>
                  <p>OpenStudy ships a <code>send_telegram</code> MCP tool — wire it to a cron, get briefed before every lecture.</p>
                </figcaption>
              </figure>
            </article>
          </div>
        </section>

        {/* ==================== SELF-HOST ==================== */}
        <section className="sec container" id="selfhost">
          <div className="sec-label">§ 04 / Self-host</div>
          <h2 className="sec-h">One docker compose.</h2>

          <div className="terminal">
            <div className="body">
              <span className="line"><span className="dol">$</span>git clone https://github.com/openstudy-dev/OpenStudy</span>
              <span className="line"><span className="dol">$</span>cd OpenStudy</span>
              <span className="line"><span className="dol">$</span>cp .env.example .env</span>
              <span className="line"><span className="dol">$</span>vim .env              <span className="cmt"># APP_PASSWORD_HASH, SESSION_SECRET</span></span>
              <span className="line"><span className="dol">$</span>vim .env.docker       <span className="cmt"># POSTGRES_USER / _PASSWORD / _DB</span></span>
              <span className="line"><span className="dol">$</span>./deploy.sh</span>
              <span className="line"><span className="out">  ✓ openstudy-postgres   (internal)</span></span>
              <span className="line"><span className="out">  ✓ openstudy-api        :8000</span></span>
              <span className="line"><span className="out">  ✓ openstudy-frontend   :8080</span></span>
              <span className="line"> </span>
              <span className="line"><span className="dol">$</span>claude mcp add --transport http openstudy https://your-domain/mcp</span>
              <span className="line"><span className="ok">  ✓ handshake ok · 44 tools available</span></span>
            </div>
          </div>
        </section>

        {/* ==================== FINAL CTA ==================== */}
        <section className="final">
          <div className="container">
            <h2>Let Claude/ChatGPT run <em>the boring half</em> of your semester.</h2>
            <div className="hero-ctas" style={{ marginTop: "2rem", marginBottom: "-2rem" }}>
              <GhCta label="GitHub" stars={stars} />
              <a className="cta-secondary" href={INSTALL_URL} target="_blank" rel="noopener noreferrer">
                Install guide
              </a>
            </div>
          </div>
        </section>

        {/* ==================== FOOTER ==================== */}
        <footer className="container">
          <div className="footer">
            <div>
              <div className="fbrand">
                <Wordmark variant="auto-os" />
              </div>
              <div className="meta">
                © 2026 OpenStudy · <a href={`${GH_URL}/blob/main/LICENSE`}>MIT licensed</a>
              </div>
            </div>
            <div className="flinks">
              <GhPill stars={stars} />
              <a href={INSTALL_URL}>Install guide</a>
              <a href="mailto:hello@openstudy.dev">Contact</a>
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
}
