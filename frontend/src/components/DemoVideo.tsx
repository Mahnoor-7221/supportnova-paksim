import { useCallback, useEffect, useRef, useState } from "react";

const SRC = "/PakSim-Walkthrough.mp4";

/** Autoplaying, muted, looping demo video with poster + graceful fallback. */
export default function DemoVideo() {
  const ref = useRef<HTMLVideoElement>(null);
  const [failed, setFailed] = useState(false);
  const [blocked, setBlocked] = useState(false);

  const tryPlay = useCallback(() => {
    const v = ref.current;
    if (!v) return;
    v.muted = true;
    v.loop = true;
    v.play().then(() => setBlocked(false)).catch(() => setBlocked(true));
  }, []);

  useEffect(() => {
    tryPlay();
    const v = ref.current;
    // Safety net: if a browser ever fires "ended" despite loop, restart.
    const restart = () => { if (v) { v.currentTime = 0; tryPlay(); } };
    // Resume when tab becomes visible again; retry on first user gesture.
    const vis = () => { if (!document.hidden) tryPlay(); };
    document.addEventListener("visibilitychange", vis);
    window.addEventListener("pointerdown", tryPlay, { once: true });
    v?.addEventListener("ended", restart);
    return () => {
      document.removeEventListener("visibilitychange", vis);
      window.removeEventListener("pointerdown", tryPlay);
      v?.removeEventListener("ended", restart);
    };
  }, [tryPlay]);

  if (failed) {
    return (
      <div className="pp-video-fallback" role="img" aria-label="PakSim walkthrough preview">
        <img src="/poster.svg" alt="" />
        <div>
          <strong>Demo video is not available right now</strong>
          <p>Aap phir bhi login karke Nova ko live try kar sakte hain.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="pp-video">
      <video
        ref={ref}
        className="lp-video"
        autoPlay
        muted
        loop
        playsInline
        preload="auto"
        poster="/poster.svg"
        aria-label="PakSim customer support walkthrough"
        onError={() => setFailed(true)}
      >
        <source src={SRC} type="video/mp4" />
      </video>
      {blocked && (
        <button type="button" className="pp-video-play" onClick={tryPlay}>▶ Tap to play</button>
      )}
    </div>
  );
}
