export function seekMilliseconds(
  clientX: number,
  left: number,
  width: number,
  durationMs: number,
): number {
  if (!Number.isFinite(width) || width <= 0 || durationMs <= 0) return 0;
  const fraction = Math.max(0, Math.min(1, (clientX - left) / width));
  return Math.round(fraction * durationMs);
}

export function waveformTime(milliseconds: number): string {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  return hours
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
    : `${minutes}:${String(remainder).padStart(2, "0")}`;
}

export function smoothWaveformPeaks(peaks: readonly number[]): number[] {
  const weights = [1, 2, 3, 4, 3, 2, 1];
  return peaks.map((_, index) => {
    let weighted = 0;
    let total = 0;
    for (let offset = -3; offset <= 3; offset += 1) {
      const neighbor = peaks[index + offset];
      if (neighbor === undefined) continue;
      const weight = weights[offset + 3];
      weighted += Math.max(0, Math.min(1, neighbor)) * weight;
      total += weight;
    }
    return total ? weighted / total : 0;
  });
}

export function waveformShape(peaks: readonly number[]): string {
  if (!peaks.length) return "";
  const smoothed = smoothWaveformPeaks(peaks);
  const upper = smoothed.map((peak) => 44 - peak * 38);
  const lower = smoothed.map((peak) => 44 + peak * 38);
  const curve = (values: number[], reverse: boolean) => {
    const indexes = values.map((_, index) => index);
    if (reverse) indexes.reverse();
    let result = `L ${indexes[0]} ${values[indexes[0]].toFixed(2)}`;
    for (let index = 0; index < indexes.length - 1; index += 1) {
      const current = indexes[index];
      const next = indexes[index + 1];
      result += ` Q ${current} ${values[current].toFixed(2)} ${((current + next) / 2).toFixed(2)} ${((values[current] + values[next]) / 2).toFixed(2)}`;
    }
    const last = indexes[indexes.length - 1];
    return `${result} L ${last} ${values[last].toFixed(2)}`;
  };
  return `M 0 44 ${curve(upper, false)} ${curve(lower, true)} Z`;
}

export function togglePlaybackAt(
  audio: Pick<
    HTMLAudioElement,
    "currentTime" | "paused" | "ended" | "play" | "pause"
  >,
  milliseconds: number,
): Promise<void> {
  const shouldPlay = audio.paused || audio.ended;
  audio.currentTime = milliseconds / 1000;
  if (shouldPlay) return audio.play();
  audio.pause();
  return Promise.resolve();
}

export function followAudioPlayback(
  audio: Pick<
    HTMLAudioElement,
    "paused" | "ended" | "addEventListener" | "removeEventListener"
  >,
  renderPosition: () => void,
  requestFrame: typeof requestAnimationFrame = requestAnimationFrame,
  cancelFrame: typeof cancelAnimationFrame = cancelAnimationFrame,
): () => void {
  let frame: number | null = null;
  const animate = () => {
    frame = null;
    renderPosition();
    if (!audio.paused && !audio.ended) frame = requestFrame(animate);
  };
  const start = () => {
    if (frame === null) frame = requestFrame(animate);
  };
  const stop = () => {
    if (frame !== null) cancelFrame(frame);
    frame = null;
    renderPosition();
  };
  audio.addEventListener("play", start);
  audio.addEventListener("pause", stop);
  audio.addEventListener("ended", stop);
  audio.addEventListener("seeked", renderPosition);
  audio.addEventListener("timeupdate", renderPosition);
  renderPosition();
  if (!audio.paused) start();
  return () => {
    if (frame !== null) cancelFrame(frame);
    audio.removeEventListener("play", start);
    audio.removeEventListener("pause", stop);
    audio.removeEventListener("ended", stop);
    audio.removeEventListener("seeked", renderPosition);
    audio.removeEventListener("timeupdate", renderPosition);
  };
}
