import { useEffect, useRef } from "react";
import "./Loginbg.css";

/*
  Login background: a soft grid, a slow-breathing glow behind the card, and a drifting particle network.
  Nodes link up when close, push away from the cursor, and lime threads reach from the cursor to nearby nodes.
  Pure canvas + CSS (no dependencies). Pauses with the tab, and is static for prefers-reduced-motion.
*/
const LINK = 140;
const REACH = 190;
const REPEL = 150;

export default function LoginBackground({ behind = false }) {
  const ref = useRef(null);

  useEffect(() => {
    const c = ref.current;
    const ctx = c.getContext("2d");
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let w = 0, h = 0, raf = 0, nodes = [];
    const mouse = { x: -9999, y: -9999, on: false };

    const resize = () => {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      w = window.innerWidth; h = window.innerHeight;
      c.width = w * dpr; c.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const n = Math.min(90, Math.round((w * h) / 16000));
      nodes = Array.from({ length: n }, () => ({
        x: Math.random() * w, y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.28, vy: (Math.random() - 0.5) * 0.28,
        r: 1 + Math.random() * 1.7, lime: Math.random() < 0.12,
      }));
      if (reduce) draw(false);
    };

    function draw(step = true) {
      ctx.clearRect(0, 0, w, h);

      if (mouse.on) {
        const g = ctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, 240);
        g.addColorStop(0, "rgba(31,75,255,0.22)");
        g.addColorStop(1, "rgba(31,75,255,0)");
        ctx.fillStyle = g;
        ctx.fillRect(mouse.x - 240, mouse.y - 240, 480, 480);
      }

      for (const n of nodes) {
        if (step) {
          n.x += n.vx; n.y += n.vy;
          if (n.x < -10) n.x = w + 10; else if (n.x > w + 10) n.x = -10;
          if (n.y < -10) n.y = h + 10; else if (n.y > h + 10) n.y = -10;
          if (mouse.on) {
            const dx = n.x - mouse.x, dy = n.y - mouse.y, d = Math.hypot(dx, dy);
            if (d < REPEL && d > 0.1) { const f = (1 - d / REPEL) * 0.9; n.x += (dx / d) * f; n.y += (dy / d) * f; }
          }
        }
      }

      ctx.lineWidth = 1;
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          const d = Math.hypot(a.x - b.x, a.y - b.y);
          if (d < LINK) {
            ctx.strokeStyle = `rgba(59,107,255,${((1 - d / LINK) * 0.42).toFixed(3)})`;
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          }
        }
        if (mouse.on) {
          const d = Math.hypot(a.x - mouse.x, a.y - mouse.y);
          if (d < REACH) {
            ctx.strokeStyle = `rgba(198,255,0,${((1 - d / REACH) * 0.55).toFixed(3)})`;
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(mouse.x, mouse.y); ctx.stroke();
          }
        }
      }

      for (const n of nodes) {
        ctx.fillStyle = n.lime ? "rgba(198,255,0,0.16)" : "rgba(59,107,255,0.20)";
        ctx.beginPath(); ctx.arc(n.x, n.y, n.r * 3.2, 0, 6.2832); ctx.fill();
        ctx.fillStyle = n.lime ? "#c6ff00" : "#3b6bff";
        ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, 6.2832); ctx.fill();
      }
    }

    const loop = () => { draw(true); raf = requestAnimationFrame(loop); };
    const onMove = (e) => { mouse.x = e.clientX; mouse.y = e.clientY; mouse.on = true; };
    const onLeave = () => { mouse.on = false; };

    resize();
    window.addEventListener("resize", resize);
    if (!reduce) {
      window.addEventListener("pointermove", onMove, { passive: true });
      document.documentElement.addEventListener("mouseleave", onLeave);
      raf = requestAnimationFrame(loop);
    }
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("mouseleave", onLeave);
    };
  }, []);

  return (
    <div className={`lb-wrap${behind ? " lb-behind" : ""}`} aria-hidden="true">
      <div className="lb-grid" />
      <div className="lb-glow" />
      <canvas ref={ref} className="lb-canvas" />
    </div>
  );
}