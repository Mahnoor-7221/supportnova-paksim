import { useCallback, useEffect, useRef, useState } from "react";

const SRC = "/PakSim-Walkthrough.mp4";

/**
 * Landing-page demo video.
 * Browsers only allow AUTOPLAY when the video is muted, so it starts muted
 * and the visitor taps "Unmute" to hear the audio.
 */
export default function DemoVideo() {
  const ref = useRef<HTMLVideoElement>(null);
  const [failed, setFailed] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [muted, setMuted] = useState(true);

  // Autoplay attempt (always muted, otherwise browsers block it)
  const tryPlay = useCallback(() => {
    const v = ref.current;
    if (!v) return;
    v.loop = true;
    v.play().then(() => setBlocked(false)).catch(() => setBlocked(true));
  }, []);

  useEffect(() => {
    const v = ref.current;
    if (v) v.muted = true; // start muted so autoplay works
    tryPlay();
    const vis = () => { if (!document.hidden) tryPlay(); };
    document.addEventListener("visibilitychange", vis);
    return () => document.removeEventListener("visibilitychange", vis);
  }, [tryPlay]);

  // Unmute / mute toggle. This click is a user gesture, so sound is allowed.
  const toggleSound = () => {
    const v = ref.current;
    if (!v) return;
    const next = !v.muted;
    v.muted = next;
    if (!next) {
      v.volume = 1;
      v.play().catch(() => {});
    }
    setMuted(next);
  };

  // "Tap to play" fallback (when even muted autoplay is blocked): play WITH sound
  const manualPlay = () => {
    const v = ref.current;
    if (!v) return;
    v.muted = false;
    v.volume = 1;
    v.play().then(() => { setBlocked(false); setMuted(false); }).catch(() => setBlocked(true));
  };

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
        onVolumeChange={(e) => setMuted((e.target as HTMLVideoElement).muted)}
      >
        <source src={SRC} type="video/mp4" />
      </video>

      {blocked && (
        <button type="button" className="pp-video-play" onClick={manualPlay}>▶ Tap to play</button>
      )}

      {!blocked && (
        <button type="button" className="pp-video-sound" onClick={toggleSound}>
          {muted ? "🔇 Tap to unmute" : "🔊 Sound on"}
        </button>
      )}
    </div>
  );
}
