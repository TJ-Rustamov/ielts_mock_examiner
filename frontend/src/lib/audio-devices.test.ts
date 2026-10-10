import { describe, expect, it } from 'vitest';
import { chooseDevice, hasUnsafeDevice, safeDevices, type AudioDevice } from './audio-devices';

const mic = (deviceId: string, label: string): AudioDevice => ({ deviceId, kind: 'audioinput', label });

// What Chrome reports on a Windows laptop with Steam's leftover driver.
const REALTEK = mic('realtek-id', 'Microphone Array (Realtek(R) Audio)');
const HEADSET = mic('headset-id', 'Microphone (AB13X USB Audio)');
const STEAM = mic('steam-id', 'Microphone (Steam Streaming Microphone)');

describe('chooseDevice', () => {
  it('never follows a default that points at the Steam microphone', () => {
    const devices = [
      mic('default', 'Default - Microphone (Steam Streaming Microphone)'),
      mic('communications', 'Communications - Microphone (Steam Streaming Microphone)'),
      STEAM, REALTEK,
    ];
    expect(chooseDevice(devices, 'audioinput')).toEqual({
      deviceId: 'realtek-id', label: REALTEK.label, reason: 'first-safe',
    });
  });

  it('follows a safe default to the real device behind it', () => {
    const devices = [mic('default', 'Default - Microphone (AB13X USB Audio)'), REALTEK, HEADSET, STEAM];
    expect(chooseDevice(devices, 'audioinput')).toEqual({
      deviceId: 'headset-id', label: HEADSET.label, reason: 'default',
    });
  });

  it('prefers the microphone the candidate chose last time', () => {
    const devices = [mic('default', 'Default - Microphone (AB13X USB Audio)'), REALTEK, HEADSET];
    expect(chooseDevice(devices, 'audioinput', 'realtek-id').reason).toBe('remembered');
    expect(chooseDevice(devices, 'audioinput', 'realtek-id').deviceId).toBe('realtek-id');
  });

  it('ignores a remembered Steam microphone', () => {
    const devices = [mic('default', 'Default - Microphone Array (Realtek(R) Audio)'), REALTEK, STEAM];
    expect(chooseDevice(devices, 'audioinput', 'steam-id').deviceId).toBe('realtek-id');
  });

  it('ignores a remembered microphone that has been unplugged', () => {
    const devices = [mic('default', 'Default - Microphone Array (Realtek(R) Audio)'), REALTEK];
    expect(chooseDevice(devices, 'audioinput', 'headset-id').deviceId).toBe('realtek-id');
  });

  it('cannot choose before the browser reveals device names', () => {
    const devices = [mic('default', ''), mic('', '')];
    expect(chooseDevice(devices, 'audioinput')).toEqual({ label: '', reason: 'unknown' });
  });

  it('refuses to choose when every microphone is unsafe', () => {
    const devices = [mic('default', 'Default - Microphone (Steam Streaming Microphone)'), STEAM];
    expect(chooseDevice(devices, 'audioinput')).toEqual({ label: '', reason: 'none-safe' });
    expect(hasUnsafeDevice(devices)).toBe(true);
  });

  it('leaves a safe but unmatched default to the browser', () => {
    const devices = [mic('default', 'Default - Some Other Mic'), REALTEK];
    expect(chooseDevice(devices, 'audioinput')).toEqual({ label: 'Some Other Mic', reason: 'default' });
  });

  it('only looks at the requested kind', () => {
    const speakers: AudioDevice = { deviceId: 'out', kind: 'audiooutput', label: 'Speakers (Realtek(R) Audio)' };
    expect(chooseDevice([speakers, STEAM], 'audioinput').reason).toBe('none-safe');
  });
});

describe('safeDevices', () => {
  it('lists real, named, safe devices without the default aliases', () => {
    const devices = [mic('default', 'Default - Microphone Array (Realtek(R) Audio)'), STEAM, REALTEK, HEADSET];
    expect(safeDevices(devices, 'audioinput').map((device) => device.deviceId))
      .toEqual(['realtek-id', 'headset-id']);
  });
});
