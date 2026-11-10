import React from 'react';
import { interpolate, Sequence, useCurrentFrame, useVideoConfig } from 'remotion';
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

export const B2BReel: React.FC<B2BReelProps> = ({ data: propData }) => {
  const data = propData || (defaultSampleData as B2BReelData);
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  const ctaStartFrame = durationInFrames - 100; // Last ~3.3 seconds for CTA

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

      {/* CTA Sequence */}
      <Sequence from={ctaStartFrame} durationInFrames={100}>
        <CtaCard cta={data.cta} brandName={data.brandName} />
      </Sequence>
    </div>
  );
};
