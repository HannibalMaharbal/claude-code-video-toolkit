import React from 'react';
import { Audio, interpolate, Sequence, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { AnimatedBackground } from './components/AnimatedBackground';
import { HeaderHook } from './components/HeaderHook';
import { StatCard } from './components/StatCard';
import { KeyPointsList } from './components/KeyPointsList';
import { WordCaptions } from './components/WordCaptions';
import { CtaCard } from './components/CtaCard';
import { B2BReelData } from './types';
import defaultSampleData from '../sample-data.json';

export interface B2BReelProps {
  data?: B2BReelData;
}

const isAllowedAudioSrc = (src?: string): src is string => {
  if (!src) return false;
  if (src.includes('://') || src.startsWith('/') || !src.startsWith('_runtime_voiceover/')) {
    return false;
  }
  const segments = src.split('/');
  return !segments.some((seg) => seg === '..' || seg === '.');
};

export const B2BReel: React.FC<B2BReelProps> = ({ data: propData }) => {
  const data = propData || (defaultSampleData as B2BReelData);
  const frame = useCurrentFrame();
  const { durationInFrames, fps } = useVideoConfig();

  const ctaDurationInFrames = Math.round(3.5 * fps);
  const ctaStartFrame = durationInFrames - ctaDurationInFrames;

  const bodyOpacity = interpolate(
    frame,
    [ctaStartFrame - 15, ctaStartFrame],
    [1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );

  return (
    <div
      style={{
        position: 'relative',
        width: 1080,
        height: 1920,
        overflow: 'hidden',
        fontFamily: 'system-ui, -apple-system, sans-serif',
      }}
    >
      <AnimatedBackground />

      {/* Main Content Body */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          opacity: bodyOpacity,
          pointerEvents: bodyOpacity === 0 ? 'none' : 'auto',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <HeaderHook
          brandName={data.brandName}
          brandTagline={data.brandTagline}
          badgeText={data.badgeText}
          hookHeadline={data.hookHeadline}
          hookSubline={data.hookSubline}
        />

        <StatCard stat={data.statHighlight} />

        <KeyPointsList points={data.keyPoints} />

        <WordCaptions captions={data.captions} />
      </div>

      {/* Voiceover Audio */}
      {isAllowedAudioSrc(data.audioSrc) && (
        <Audio src={staticFile(data.audioSrc)} />
      )}

      {/* Audio SFX Cues */}
      <Sequence from={0} durationInFrames={30}>
        <Audio src={staticFile("sfx/bass_impact.mp3")} volume={0.3} />
      </Sequence>
      <Sequence from={15} durationInFrames={15}>
        <Audio src={staticFile("sfx/ui_pop_clean.mp3")} volume={0.2} />
      </Sequence>
      <Sequence from={24} durationInFrames={20}>
        <Audio src={staticFile("sfx/whoosh_subtle.mp3")} volume={0.15} />
      </Sequence>
      <Sequence from={ctaStartFrame} durationInFrames={30}>
        <Audio src={staticFile("sfx/gold_shimmer.mp3")} volume={0.25} />
      </Sequence>

      {/* CTA Sequence */}
      <Sequence from={ctaStartFrame} durationInFrames={ctaDurationInFrames}>
        <CtaCard cta={data.cta} brandName={data.brandName} />
      </Sequence>
    </div>
  );
};
