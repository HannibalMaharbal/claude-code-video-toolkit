import React from 'react';
import { spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { CallToAction } from '../types';

interface CtaCardProps {
  cta: CallToAction;
  brandName: string;
}

export const CtaCard: React.FC<CtaCardProps> = ({ cta, brandName }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const entrance = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 120 },
  });

  const pulse = Math.sin(frame / 10) * 0.04 + 1;

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: 1080,
        height: 1920,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '0 80px',
        boxSizing: 'border-box',
        zIndex: 5,
        textAlign: 'center',
      }}
    >
      <div
        style={{
          transform: `scale(${entrance})`,
          opacity: entrance,
          width: '100%',
          background: 'linear-gradient(180deg, rgba(15, 23, 42, 0.95) 0%, rgba(7, 9, 14, 0.98) 100%)',
          border: '2px solid rgba(212, 175, 55, 0.6)',
          borderRadius: '32px',
          padding: '64px 48px',
          boxShadow: '0 24px 64px rgba(0, 0, 0, 0.8), 0 0 40px rgba(212, 175, 55, 0.2)',
          boxSizing: 'border-box',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
        }}
      >
        {/* Brand Tag */}
        <div
          style={{
            fontSize: '26px',
            fontWeight: 800,
            letterSpacing: '5px',
            color: '#D4AF37',
            marginBottom: '24px',
            textTransform: 'uppercase',
            fontFamily: 'system-ui, -apple-system, sans-serif',
          }}
        >
          {brandName}
        </div>

        {/* CTA Headline */}
        <h2
          style={{
            fontSize: '52px',
            fontWeight: 900,
            lineHeight: 1.15,
            color: '#FFFFFF',
            margin: '0 0 24px 0',
            textTransform: 'uppercase',
            fontFamily: 'system-ui, -apple-system, sans-serif',
          }}
        >
          {cta.headline}
        </h2>

        {/* CTA Subline */}
        <p
          style={{
            fontSize: '28px',
            fontWeight: 400,
            color: '#CBD5E1',
            lineHeight: 1.4,
            margin: '0 0 48px 0',
            maxWidth: '750px',
            fontFamily: 'system-ui, -apple-system, sans-serif',
          }}
        >
          {cta.subline}
        </p>

        {/* Action Button */}
        <div
          style={{
            transform: `scale(${pulse})`,
            background: 'linear-gradient(90deg, #D4AF37 0%, #F59E0B 100%)',
            borderRadius: '999px',
            padding: '24px 60px',
            boxShadow: '0 12px 32px rgba(212, 175, 55, 0.4)',
          }}
        >
          <span
            style={{
              fontSize: '32px',
              fontWeight: 800,
              color: '#07090E',
              letterSpacing: '2px',
              textTransform: 'uppercase',
              fontFamily: 'system-ui, -apple-system, sans-serif',
            }}
          >
            {cta.badge}
          </span>
        </div>

        {cta.url && (
          <div
            style={{
              marginTop: '36px',
              fontSize: '26px',
              fontWeight: 600,
              color: '#94A3B8',
              letterSpacing: '1px',
              fontFamily: 'system-ui, -apple-system, sans-serif',
            }}
          >
            {cta.url}
          </div>
        )}
      </div>
    </div>
  );
};
