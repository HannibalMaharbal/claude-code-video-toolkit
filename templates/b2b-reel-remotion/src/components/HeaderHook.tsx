import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';

interface HeaderHookProps {
  brandName: string;
  brandTagline?: string;
  badgeText: string;
  hookHeadline: string;
  hookSubline: string;
}

export const HeaderHook: React.FC<HeaderHookProps> = ({
  brandName,
  brandTagline,
  badgeText,
  hookHeadline,
  hookSubline,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const badgeSpring = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 120 },
  });

  const headlineSpring = spring({
    frame: frame - 6,
    fps,
    config: { damping: 16, stiffness: 100 },
  });

  const sublineOpacity = interpolate(frame, [15, 30], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        textAlign: 'center',
        padding: '120px 60px 0 60px',
        width: '100%',
        boxSizing: 'border-box',
        zIndex: 2,
      }}
    >
      {/* Brand header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          marginBottom: '32px',
          opacity: 0.85,
        }}
      >
        <div
          style={{
            width: 14,
            height: 14,
            backgroundColor: '#D4AF37',
            transform: 'rotate(45deg)',
          }}
        />
        <span
          style={{
            fontSize: '28px',
            fontWeight: 800,
            letterSpacing: '4px',
            color: '#FFFFFF',
            fontFamily: 'system-ui, -apple-system, sans-serif',
          }}
        >
          {brandName}
        </span>
        {brandTagline && (
          <span
            style={{
              fontSize: '22px',
              fontWeight: 400,
              color: '#94A3B8',
              letterSpacing: '2px',
              fontFamily: 'system-ui, -apple-system, sans-serif',
            }}
          >
            | {brandTagline}
          </span>
        )}
      </div>

      {/* Pill Badge */}
      <div
        style={{
          transform: `scale(${badgeSpring})`,
          opacity: badgeSpring,
          backgroundColor: 'rgba(212, 175, 55, 0.12)',
          border: '1px solid rgba(212, 175, 55, 0.4)',
          borderRadius: '999px',
          padding: '10px 28px',
          marginBottom: '36px',
        }}
      >
        <span
          style={{
            color: '#F3E5AB',
            fontSize: '24px',
            fontWeight: 700,
            letterSpacing: '2px',
            textTransform: 'uppercase',
            fontFamily: 'system-ui, -apple-system, sans-serif',
          }}
        >
          {badgeText}
        </span>
      </div>

      {/* Main Hook Headline */}
      <h1
        style={{
          transform: `translateY(${(1 - headlineSpring) * 40}px)`,
          opacity: headlineSpring,
          fontSize: '56px',
          fontWeight: 900,
          lineHeight: 1.15,
          color: '#FFFFFF',
          margin: 0,
          textTransform: 'uppercase',
          letterSpacing: '-1px',
          textShadow: '0 4px 24px rgba(0,0,0,0.8)',
          fontFamily: 'system-ui, -apple-system, sans-serif',
        }}
      >
        {hookHeadline}
      </h1>

      {/* Subline */}
      <p
        style={{
          opacity: sublineOpacity,
          fontSize: '30px',
          fontWeight: 400,
          lineHeight: 1.35,
          color: '#CBD5E1',
          marginTop: '24px',
          maxWidth: '850px',
          fontFamily: 'system-ui, -apple-system, sans-serif',
        }}
      >
        {hookSubline}
      </p>
    </div>
  );
};
