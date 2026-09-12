// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EmailGatewayAnimation } from "../../../src/app/components/landing/email-gateway-animation";

// The parent asks framer-motion for one animation control per bin, in the
// order legit, spam, phishing, on every render. Cycling through three stable
// mocks keeps each bin bound to the same control across renders.
const mocks = vi.hoisted(() => {
  const controls = [0, 1, 2].map(() => ({ start: vi.fn().mockResolvedValue(undefined) }));
  return { controls, calls: 0 };
});

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
  motion: { div: "div" },
  useAnimation: () => mocks.controls[mocks.calls++ % 3],
}));

const bins = { legit: 0, spam: 1, phishing: 2 } as const;

// Math.random first picks the message type (< 0.55 legit, < 0.82 spam, else
// phishing), then the delay before the next spawn. Seeding the first draw and
// pinning the rest at 0.95 gives every scenario the same cadence: a message at
// 1000 ms, then one every 2640 ms (1500 + 0.95 * 1200). Each message is scanned
// 1000 ms after it appears, dispatched 1000 ms later and arrives 1200 ms after
// that, so the first one arrives at 4200 ms while the second is on its way in.
const typeSeed = { legit: 0.1, spam: 0.7, phishing: 0.95 } as const;

// The glow painted on the envelope face for each stage of its journey.
const glow = {
  intake: "0 0 12px rgba(59, 130, 246, 0.4)",
  scanning: "0 0 12px rgba(255, 255, 255, 0.6)",
  legit: "0 0 12px rgba(16, 185, 129, 0.5)",
  spam: "0 0 12px rgba(245, 158, 11, 0.5)",
  phishing: "0 0 12px rgba(239, 68, 68, 0.6)",
} as const;

const bounceProps = {
  scale: [1, 1.28, 0.82, 1.08, 0.95, 1],
  rotateX: [22, 12, 32, 18, 24, 22],
  rotateY: [-15, -20, -10, -17, -13, -15],
  transition: { duration: 0.65, ease: "easeOut" },
};

// Each envelope is drawn as one SVG face; the face's parent carries the glow.
function envelopeGlows(container: HTMLElement) {
  return Array.from(container.querySelectorAll('svg[viewBox="0 0 36 28"]')).map(
    (face) => (face.parentElement as HTMLElement).style.boxShadow,
  );
}

// Impact particles are the only boxes painted with a six-pixel glow.
function particles(container: HTMLElement) {
  return Array.from(container.querySelectorAll("div")).filter((box) =>
    box.style.boxShadow.startsWith("0 0 6px"),
  );
}

// An envelope is six nested boxes; anything left over once they and the
// particles are counted out is the scanner's laser sweep, which only exists
// while a scan runs.
function scannerLit(container: HTMLElement, restingBoxes: number) {
  const boxes = container.querySelectorAll("div").length;
  const known = restingBoxes + 6 * envelopeGlows(container).length + particles(container).length;
  return boxes - known === 1;
}

function seed(type: keyof typeof typeSeed) {
  vi.spyOn(Math, "random").mockReturnValueOnce(typeSeed[type]).mockReturnValue(0.95);
}

function advance(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
}

// One commit per timer, as in a browser: a single long jump would batch every
// state update into one render and hide the intermediate states.
function advanceUntil(done: () => boolean, limitMs: number, step = 250) {
  let elapsed = 0;
  while (elapsed < limitMs) {
    advance(step);
    elapsed += step;
    if (done()) return elapsed;
  }
  throw new Error(`condition not met within ${limitMs} ms`);
}

// Walk the clock in browser-sized steps so each envelope mounts, and starts its
// own timers, at the moment it is spawned rather than when the jump ends.
function stepTo(ms: number) {
  let elapsed = 0;
  while (elapsed + 100 <= ms) {
    advance(100);
    elapsed += 100;
  }
  if (elapsed < ms) advance(ms - elapsed);
}

function startCalls() {
  return mocks.controls.map((control) => control.start.mock.calls.length);
}

beforeEach(() => {
  vi.useFakeTimers();
  mocks.calls = 0;
  for (const control of mocks.controls) control.start.mockClear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("EmailGatewayAnimation", () => {
  it("renders the pipe network as decoration hidden from assistive technology, with no message yet", () => {
    seed("legit");
    const { container } = render(<EmailGatewayAnimation />);
    expect(container.querySelector('svg[viewBox="0 0 600 380"]')).toHaveAttribute("aria-hidden", "true");
    expect(container.querySelector("style")).toHaveTextContent("spinCube3D");
    expect(envelopeGlows(container)).toEqual([]);
    expect(scannerLit(container, container.querySelectorAll("div").length)).toBe(false);
  });

  it("feeds the first message in after one second and the next ones at the drawn cadence", () => {
    seed("legit");
    const { container } = render(<EmailGatewayAnimation />);
    advance(999);
    expect(envelopeGlows(container)).toEqual([]);
    advance(1);
    expect(envelopeGlows(container)).toEqual([glow.intake]);
    advance(2639);
    expect(envelopeGlows(container)).toHaveLength(1);
    advance(1);
    expect(envelopeGlows(container)).toHaveLength(2);
    expect(envelopeGlows(container)[1]).toBe(glow.intake);
  });

  it("lights the scanner and whitens the envelope one second after intake", () => {
    seed("spam");
    const { container } = render(<EmailGatewayAnimation />);
    const resting = container.querySelectorAll("div").length;
    advance(1000);
    expect(scannerLit(container, resting)).toBe(false);
    advance(999);
    expect(envelopeGlows(container)).toEqual([glow.intake]);
    expect(scannerLit(container, resting)).toBe(false);
    advance(1);
    expect(envelopeGlows(container)).toEqual([glow.scanning]);
    expect(scannerLit(container, resting)).toBe(true);
  });

  it.each(["legit", "spam", "phishing"] as const)(
    "colours a %s message with its verdict and switches the scanner off once the scan ends",
    (type) => {
      seed(type);
      const { container } = render(<EmailGatewayAnimation />);
      const resting = container.querySelectorAll("div").length;
      const scanStart = advanceUntil(() => scannerLit(container, resting), 5000);
      expect(scanStart).toBe(2000);
      expect(envelopeGlows(container)[0]).toBe(glow.scanning);

      const scanEnd = advanceUntil(() => !scannerLit(container, resting), 5000);
      expect(scanStart + scanEnd).toBe(3000);
      // The verdict colours the envelope, and the scan ended before the next message arrived.
      expect(envelopeGlows(container)).toEqual([glow[type]]);
      // The next message, drawn as phishing, comes in on its own timeline.
      advance(640);
      expect(envelopeGlows(container)).toEqual([glow[type], glow.intake]);
    },
  );

  it("keeps the bins still and the console idle until a scan ends", () => {
    seed("phishing");
    const { container } = render(<EmailGatewayAnimation />);
    const resting = container.querySelectorAll("div").length;
    advance(1000);
    expect(startCalls()).toEqual([0, 0, 0]);
    expect(scannerLit(container, resting)).toBe(false);
  });

  it.each(["legit", "spam", "phishing"] as const)(
    "delivers a %s message 3.2 seconds after intake: the envelope goes, its bin bounces once",
    (type) => {
      seed(type);
      const { container } = render(<EmailGatewayAnimation />);
      stepTo(4199);
      // Both the first message (dispatching) and the second (intake) are in flight.
      expect(envelopeGlows(container)).toEqual([glow[type], glow.intake]);
      expect(startCalls()).toEqual([0, 0, 0]);

      advance(1);
      expect(envelopeGlows(container)).toEqual([glow.intake]);
      const expected = [0, 0, 0];
      expected[bins[type]] = 1;
      expect(startCalls()).toEqual(expected);
      expect(mocks.controls[bins[type]].start).toHaveBeenCalledWith(bounceProps);
    },
  );

  it("throws six impact particles on arrival and clears them 1.2 seconds later", () => {
    seed("legit");
    const { container } = render(<EmailGatewayAnimation />);
    stepTo(4199);
    expect(particles(container)).toHaveLength(0);
    advance(1);
    const thrown = particles(container);
    expect(thrown).toHaveLength(6);
    expect(thrown.every((particle) => particle.style.backgroundColor === "rgb(16, 185, 129)")).toBe(true);
    advance(1199);
    expect(particles(container)).toHaveLength(6);
    advance(1);
    expect(particles(container)).toHaveLength(0);
  });

  it("never lets messages pile up: each one is scanned and delivered exactly once", () => {
    seed("legit");
    const { container } = render(<EmailGatewayAnimation />);
    // Messages spawn every 2640 ms and live 3200 ms, so at most two are ever in flight.
    let peak = 0;
    for (let elapsed = 0; elapsed < 20000; elapsed += 100) {
      advance(100);
      peak = Math.max(peak, envelopeGlows(container).length);
    }
    expect(peak).toBe(2);
    // Seven messages spawned by 20 s (1000 + 6 * 2640 = 16840); six have arrived.
    expect(startCalls().reduce((sum, calls) => sum + calls, 0)).toBe(6);
  });

  it("clears every pending timer when it unmounts", () => {
    seed("legit");
    const { unmount } = render(<EmailGatewayAnimation />);
    advance(2000);
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
