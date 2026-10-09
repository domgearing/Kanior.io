import { describe, expect, it } from "vitest";

import {
  followAudioPlayback,
  seekMilliseconds,
  smoothWaveformPeaks,
  togglePlaybackAt,
  waveformShape,
  waveformTime,
} from "./waveform";

describe("waveform seeking", () => {
  it("maps pointer positions to bounded recording time", () => {
    expect(seekMilliseconds(150, 100, 200, 60_000)).toBe(15_000);
    expect(seekMilliseconds(50, 100, 200, 60_000)).toBe(0);
    expect(seekMilliseconds(400, 100, 200, 60_000)).toBe(60_000);
    expect(seekMilliseconds(150, 100, 0, 60_000)).toBe(0);
  });

  it("formats long recordings", () => {
    expect(waveformTime(5_000)).toBe("0:05");
    expect(waveformTime(3_665_000)).toBe("1:01:05");
  });

  it("smooths isolated peaks and draws a continuous closed envelope", () => {
    expect(smoothWaveformPeaks([0, 0, 0, 1, 0, 0, 0])).toEqual([
      0.1,
      2 / 13,
      3 / 15,
      4 / 16,
      3 / 15,
      2 / 13,
      0.1,
    ]);
    expect(smoothWaveformPeaks([0, 0, 0])).toEqual([0, 0, 0]);
    const shape = waveformShape([0, 1, 0]);
    expect(shape).toMatch(/^M 0 44 L /);
    expect(shape).toContain(" Q ");
    expect(shape).toMatch(/ Z$/);
  });

  it("seeks and toggles playback with one action", async () => {
    const actions: string[] = [];
    const audio = {
      currentTime: 0,
      paused: true,
      ended: false,
      play: async () => {
        actions.push("play");
      },
      pause: () => {
        actions.push("pause");
      },
    };
    await togglePlaybackAt(audio, 12_500);
    expect(audio.currentTime).toBe(12.5);
    expect(actions).toEqual(["play"]);
    audio.paused = false;
    await togglePlaybackAt(audio, 20_000);
    expect(audio.currentTime).toBe(20);
    expect(actions).toEqual(["play", "pause"]);
  });

  it("updates every animation frame while playing and stops on pause", () => {
    const audio = Object.assign(new EventTarget(), {
      paused: true,
      ended: false,
    });
    const scheduled = new Map<number, FrameRequestCallback>();
    let nextId = 0;
    let renders = 0;
    const cleanup = followAudioPlayback(
      audio as HTMLAudioElement,
      () => {
        renders += 1;
      },
      (callback) => {
        const id = ++nextId;
        scheduled.set(id, callback);
        return id;
      },
      (id) => {
        scheduled.delete(id);
      },
    );
    expect(renders).toBe(1);
    audio.paused = false;
    audio.dispatchEvent(new Event("play"));
    expect(scheduled.size).toBe(1);
    const [id, frame] = [...scheduled][0];
    scheduled.delete(id);
    frame(16);
    expect(renders).toBe(2);
    expect(scheduled.size).toBe(1);
    audio.paused = true;
    audio.dispatchEvent(new Event("pause"));
    expect(scheduled.size).toBe(0);
    const stoppedRenders = renders;
    cleanup();
    audio.dispatchEvent(new Event("play"));
    expect(renders).toBe(stoppedRenders);
    expect(scheduled.size).toBe(0);
  });
});
