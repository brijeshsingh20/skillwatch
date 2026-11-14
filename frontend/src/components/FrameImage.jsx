import { useEffect, useState } from "react";
import { ImageOff } from "lucide-react";
import { api } from "../api.js";

/** Shows a privacy-blurred thumbnail. The image endpoint needs the login token, so it is fetched as a blob. */
export default function FrameImage({ observationId, alt = "Annotated sample frame" }) {
  const [src, setSrc] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setSrc(null);
    setFailed(false);
    if (!observationId) return undefined;
    let alive = true;
    let url = null;
    api
      .get(`/observations/${observationId}/frame`, { responseType: "blob" })
      .then((r) => {
        if (!alive) return;
        url = URL.createObjectURL(r.data);
        setSrc(url);
      })
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [observationId]);

  if (!observationId || failed) {
    return (
      <div className="flex h-40 items-center justify-center gap-2 rounded-md bg-slate-100 text-sm text-slate-500">
        <ImageOff className="h-4 w-4" /> No sample frame
      </div>
    );
  }
  if (!src) return <div className="h-40 animate-pulse rounded-md bg-slate-100" />;
  return <img src={src} alt={alt} className="w-full rounded-md border border-slate-200" />;
}
