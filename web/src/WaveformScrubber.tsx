import { useEffect, useId, useMemo, useRef, type RefObject } from "react";

import {
  followAudioPlayback,
  seekMilliseconds,
  waveformShape,
  waveformTime,
} from "./waveform";

type Waveform = { duration_ms: number; peaks: number[] };

export function WaveformScrubber({
  waveform,
  positionMs,
  audioRef,
  onSeek,
  onToggleAt,
}: {
  waveform: Waveform;
  positionMs: number;
  audioRef: RefObject<HTMLAudioElement | null>;
  onSeek: (milliseconds: number) => void;
  onToggleAt: (milliseconds: number) => void;
}) {
  const pointer = useRef<{
    id: number;
    startX: number;
    dragged: boolean;
  } | null>(null);
  const clipId = useId();
  const sliderRef = useRef<HTMLDivElement>(null);
  const playedClipRef = useRef<SVGRectElement>(null);
  const playheadRef = useRef<SVGLineElement>(null);
  const currentTimeRef = useRef<HTMLSpanElement>(null);
  const shape = useMemo(() => waveformShape(waveform.peaks), [waveform.peaks]);
  const duration = waveform.duration_ms;
  const position = Math.max(0, Math.min(positionMs, duration));
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || duration <= 0) return;
    const renderPosition = () => {
      const milliseconds = Math.max(
        0,
        Math.min(audio.currentTime * 1000, duration),
      );
      const x = (milliseconds / duration) * 320;
      playheadRef.current?.setAttribute("x1", String(x));
      playheadRef.current?.setAttribute("x2", String(x));
      playedClipRef.current?.setAttribute("width", String(x));
      if (currentTimeRef.current)
        currentTimeRef.current.textContent = waveformTime(milliseconds);
      sliderRef.current?.setAttribute(
        "aria-valuenow",
        String(Math.round(milliseconds / 1000)),
      );
      sliderRef.current?.setAttribute(
        "aria-valuetext",
        `${waveformTime(milliseconds)} of ${waveformTime(duration)}`,
      );
    };
    return followAudioPlayback(audio, renderPosition);
  }, [audioRef, duration]);
  const seekFromPointer = (event: React.PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return seekMilliseconds(event.clientX, rect.left, rect.width, duration);
  };
  return (
    <div className="waveform-block">
      <div className="waveform-heading">
        <strong>Recording waveform</strong>
        <span>Click to play or pause · Drag to seek</span>
      </div>
      <div
        ref={sliderRef}
        className="waveform-scrubber"
        role="slider"
        tabIndex={0}
        aria-label="Recording waveform. Click to play or pause, drag or use arrow keys to seek"
        aria-valuemin={0}
        aria-valuemax={Math.ceil(duration / 1000)}
        aria-valuenow={Math.round(position / 1000)}
        aria-valuetext={`${waveformTime(position)} of ${waveformTime(duration)}`}
        onPointerDown={(event) => {
          pointer.current = {
            id: event.pointerId,
            startX: event.clientX,
            dragged: false,
          };
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          const active = pointer.current;
          if (!active || active.id !== event.pointerId) return;
          if (Math.abs(event.clientX - active.startX) > 4)
            active.dragged = true;
          if (active.dragged) onSeek(seekFromPointer(event));
        }}
        onPointerUp={(event) => {
          if (pointer.current?.id !== event.pointerId) return;
          const milliseconds = seekFromPointer(event);
          if (pointer.current.dragged) onSeek(milliseconds);
          else onToggleAt(milliseconds);
          pointer.current = null;
        }}
        onPointerCancel={() => {
          pointer.current = null;
        }}
        onKeyDown={(event) => {
          const actualPosition = audioRef.current
            ? Math.max(
                0,
                Math.min(audioRef.current.currentTime * 1000, duration),
              )
            : position;
          if (event.key === " " || event.key === "Enter") {
            event.preventDefault();
            onToggleAt(actualPosition);
            return;
          }
          const step = event.shiftKey ? 15_000 : 5_000;
          const target =
            event.key === "ArrowRight"
              ? actualPosition + step
              : event.key === "ArrowLeft"
                ? actualPosition - step
                : event.key === "Home"
                  ? 0
                  : event.key === "End"
                    ? duration
                    : null;
          if (target === null) return;
          event.preventDefault();
          onSeek(Math.max(0, Math.min(target, duration)));
        }}
      >
        <svg viewBox="0 0 320 88" preserveAspectRatio="none" aria-hidden="true">
          <line x1="0" x2="320" y1="44" y2="44" className="waveform-midline" />
          <defs>
            <clipPath id={clipId}>
              <rect
                ref={playedClipRef}
                x="0"
                y="0"
                width={(position / duration) * 320}
                height="88"
              />
            </clipPath>
          </defs>
          <path d={shape} className="waveform-bar" />
          <path
            d={shape}
            className="waveform-bar played"
            clipPath={`url(#${clipId})`}
          />
          <line
            ref={playheadRef}
            x1={(position / duration) * 320}
            x2={(position / duration) * 320}
            y1="0"
            y2="88"
            className="waveform-playhead"
          />
        </svg>
      </div>
      <div className="waveform-times">
        <span ref={currentTimeRef}>{waveformTime(position)}</span>
        <span>{waveformTime(duration)}</span>
      </div>
    </div>
  );
}
