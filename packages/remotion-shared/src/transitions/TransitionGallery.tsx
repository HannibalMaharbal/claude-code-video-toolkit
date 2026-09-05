/**
 * Transition Gallery
 *
 * A visual showcase of all available transitions.
 * Each transition is demonstrated with consistent before/after scenes,
 * labeled clearly for easy comparison.
 *
 * Can be:
 * 1. Rendered as a showcase video
 * 2. Used with @remotion/player for interactive preview
 *
 * Total duration: ~20 seconds at 30fps
 */
import React from 'react';
import { AbsoluteFill, useCurrentFrame, interpolate, Sequence } from 'remotion';
import { TransitionSeries, linearTiming } from '@remotion/transitions';
import type { TransitionPresentation } from '@remotion/transitions';
import { slide } from '@remotion/transitions/slide';
import { fade } from '@remotion/transitions/fade';
import { wipe } from '@remotion/transitions/wipe';
import { flip } from '@remotion/transitions/flip';
import { glitch } from './presentations/glitch';
import { rgbSplit } from './presentations/rgb-split';
import { zoomBlur } from './presentations/zoom-blur';
import { lightLeak } from './presentations/light-leak';
import { clockWipe } from './presentations/clock-wipe';
import { pixelate } from './presentations/pixelate';

// Scene colors for visual variety
const SCENE_A_COLOR = '#1a1a2e';
const SCENE_B_COLOR = '#e94560';

// Consistent scene component
const GalleryScene: React.FC<{
  color: string;
  label: string;
  isAfter?: boolean;
}> = ({ color, label, isAfter = false }) => {
  const frame = useCurrentFrame();
  const labelOpacity = interpolate(frame, [0, 10], [0, 1], {
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: color,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        fontFamily: "'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif",
      }}
    >
      {/* Transition name label */}
      <div
        style={{
          position: 'absolute',
          top: 60,
          left: 0,
          right: 0,
          textAlign: 'center',
          opacity: labelOpacity,
        }}
      >
        <span
          style={{
            fontSize: 28,
            fontWeight: 600,
            color: 'white',
            backgroundColor: 'rgba(0, 0, 0, 0.4)',
            padding: '12px 32px',
            borderRadius: 8,
            letterSpacing: '0.5px',
          }}
        >
          {label}
        </span>
      </div>

      {/* Before/After indicator */}
      <div
        style={{
          fontSize: 120,
          fontWeight: 800,
          color: 'rgba(255, 255, 255, 0.15)',
          letterSpacing: '-4px',
        }}
      >
        {isAfter ? 'B' : 'A'}
      </div>

      {/* Scene indicator */}
      <div
        style={{
          position: 'absolute',
          bottom: 60,
          fontSize: 18,
          color: 'rgba(255, 255, 255, 0.5)',
          fontWeight: 500,
        }}
      >
        {isAfter ? 'After' : 'Before'}
      </div>
    </AbsoluteFill>
  );
};

// Single transition demo segment
const TransitionDemo = <PresentationProps extends Record<string, unknown>>({
  name,
  presentation,
  transitionDuration = 20,
}: {
  name: string;
  presentation: TransitionPresentation<PresentationProps>;
  transitionDuration?: number;
}) => {
  const sceneDuration = 45; // 1.5 seconds per scene

  return (
    <TransitionSeries>
      <TransitionSeries.Sequence durationInFrames={sceneDuration}>
        <GalleryScene color={SCENE_A_COLOR} label={name} />
      </TransitionSeries.Sequence>
      <TransitionSeries.Transition
        presentation={presentation}
        timing={linearTiming({ durationInFrames: transitionDuration })}
      />
      <TransitionSeries.Sequence durationInFrames={sceneDuration}>
        <GalleryScene color={SCENE_B_COLOR} label={name} isAfter />
      </TransitionSeries.Sequence>
    </TransitionSeries>
  );
};

const createTransition = <PresentationProps extends Record<string, unknown>>(
  name: string,
  presentation: TransitionPresentation<PresentationProps>,
  duration: number,
) => ({
  name,
  presentation,
  duration,
  render: () => (
    <TransitionDemo
      name={name}
      presentation={presentation}
      transitionDuration={duration}
    />
  ),
});

// Intro slide
const IntroSlide: React.FC = () => {
  const frame = useCurrentFrame();
  const titleOpacity = interpolate(frame, [0, 20], [0, 1], { extrapolateRight: 'clamp' });
  const subtitleOpacity = interpolate(frame, [15, 35], [0, 1], { extrapolateRight: 'clamp' });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: '#0f0f1a',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        fontFamily: "'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif",
      }}
    >
      <h1
        style={{
          fontSize: 72,
          fontWeight: 700,
          color: 'white',
          margin: 0,
          opacity: titleOpacity,
          letterSpacing: '-2px',
        }}
      >
        Transitions Gallery
      </h1>
      <p
        style={{
          fontSize: 24,
          color: 'rgba(255, 255, 255, 0.6)',
          marginTop: 20,
          opacity: subtitleOpacity,
          fontWeight: 400,
        }}
      >
        claude-code-video-toolkit
      </p>
    </AbsoluteFill>
  );
};

// Define all transitions to showcase
const TRANSITIONS = [
  createTransition('glitch()', glitch({ intensity: 0.9 }), 25),
  createTransition('rgbSplit()', rgbSplit({ direction: 'horizontal' }), 25),
  createTransition('zoomBlur()', zoomBlur({ direction: 'in' }), 25),
  createTransition('lightLeak()', lightLeak({ temperature: 'warm' }), 35),
  createTransition('clockWipe()', clockWipe({ direction: 'clockwise' }), 25),
  createTransition('pixelate()', pixelate({ maxBlockSize: 50 }), 25),
  createTransition('slide()', slide(), 20),
  createTransition('fade()', fade(), 25),
  createTransition('wipe()', wipe(), 20),
  createTransition('flip()', flip(), 25),
];

// Calculate segment duration (scene + transition + scene, minus overlap)
const getSegmentDuration = (transitionDuration: number) => {
  const sceneDuration = 45;
  return sceneDuration * 2 - transitionDuration;
};

export const TransitionGallery: React.FC = () => {
  const introDuration = 60; // 2 seconds

  let currentFrame = introDuration;
  const segments: { name: string; from: number; duration: number }[] = [];

  TRANSITIONS.forEach((t) => {
    const duration = getSegmentDuration(t.duration);
    segments.push({ name: t.name, from: currentFrame, duration });
    currentFrame += duration;
  });

  return (
    <AbsoluteFill style={{ backgroundColor: '#0f0f1a' }}>
      {/* Intro */}
      <Sequence durationInFrames={introDuration}>
        <IntroSlide />
      </Sequence>

      {/* Each transition demo */}
      {TRANSITIONS.map((t, i) => (
        <Sequence
          key={t.name}
          from={segments[i].from}
          durationInFrames={segments[i].duration}
        >
          {t.render()}
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};

// Export configuration for Remotion
export const transitionGalleryConfig = {
  id: 'TransitionGallery',
  component: TransitionGallery,
  durationInFrames: 60 + TRANSITIONS.reduce(
    (acc, t) => acc + getSegmentDuration(t.duration),
    0
  ),
  fps: 30,
  width: 1920,
  height: 1080,
};

// For single-transition preview (useful for interactive player)
export const SingleTransitionPreview: React.FC<{
  transitionName: keyof typeof transitionMap;
}> = ({ transitionName }) => {
  const transition = transitionMap[transitionName];
  if (!transition) return null;

  return (
    transition.render()
  );
};

// Map for programmatic access
export const transitionMap = {
  glitch: createTransition('glitch', glitch({ intensity: 0.9 }), 25),
  rgbSplit: createTransition('rgbSplit', rgbSplit({ direction: 'horizontal' }), 25),
  zoomBlur: createTransition('zoomBlur', zoomBlur({ direction: 'in' }), 25),
  lightLeak: createTransition('lightLeak', lightLeak({ temperature: 'warm' }), 35),
  clockWipe: createTransition('clockWipe', clockWipe({ direction: 'clockwise' }), 25),
  pixelate: createTransition('pixelate', pixelate({ maxBlockSize: 50 }), 25),
  slide: createTransition('slide', slide(), 20),
  fade: createTransition('fade', fade(), 25),
  wipe: createTransition('wipe', wipe(), 20),
  flip: createTransition('flip', flip(), 25),
} as const;

export type TransitionName = keyof typeof transitionMap;
