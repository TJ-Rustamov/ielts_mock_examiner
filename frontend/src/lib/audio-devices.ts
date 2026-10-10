/**
 * Choosing audio devices without touching the ones known to crash Windows.
 *
 * Steam installs virtual "Steam Streaming Microphone" / "Steam Streaming
 * Speakers" drivers that are left behind when Steam is uninstalled. On current
 * Windows 11 the microphone driver bugchecks the whole machine
 * (DRIVER_IRQL_NOT_LESS_OR_EQUAL in SteamStreamingMicrophone.sys) as soon as a
 * browser opens it. A page that asks for "the default microphone" opens it
 * whenever Windows has made it the default, which happens on its own when a
 * headset is unplugged. So the speaking test picks a device explicitly and
 * never picks one of these.
 *
 * Only possible once the site has microphone permission: before that the
 * browser hides device names, and the first permission prompt opens the
 * default device whatever the page asks for.
 */

/** Devices known to crash the operating system when opened. */
export const UNSAFE_AUDIO_DEVICE = /steam streaming/i;

/** Chrome's aliases for "whatever Windows has chosen". Never a real device. */
const ALIAS_IDS = new Set(['default', 'communications']);
const ALIAS_PREFIX = /^(?:default|communications)\s*-\s*/i;

const MICROPHONE_KEY = 'speaking.microphoneId';

/** The parts of MediaDeviceInfo this module reads, so tests can pass plain objects. */
export interface AudioDevice {
  deviceId: string;
  kind: MediaDeviceKind;
  label: string;
}

export type ChoiceReason =
  | 'remembered'   // the device the candidate picked last time
  | 'default'      // what Windows uses by default, and it is safe
  | 'first-safe'   // the default is unsafe or unknown; first safe device instead
  | 'unknown'      // no device names yet (no permission); cannot choose
  | 'none-safe';   // every named device is unsafe: do not open anything

export interface DeviceChoice {
  /** Pass as `{ exact: deviceId }`. Undefined: let the browser use its default. */
  deviceId?: string;
  label: string;
  reason: ChoiceReason;
}

export function isUnsafeDevice(device: Pick<AudioDevice, 'label'>): boolean {
  return UNSAFE_AUDIO_DEVICE.test(device.label);
}

export function hasUnsafeDevice(devices: AudioDevice[]): boolean {
  return devices.some(isUnsafeDevice);
}

/** Real, named, safe devices of one kind, in the browser's order. */
export function safeDevices(devices: AudioDevice[], kind: MediaDeviceKind): AudioDevice[] {
  return devices.filter((device) =>
    device.kind === kind
    && device.label
    && !ALIAS_IDS.has(device.deviceId)
    && !isUnsafeDevice(device));
}

/** Pick the device to open for `kind`. Pure, so it can be tested without a browser. */
export function chooseDevice(
  devices: AudioDevice[],
  kind: MediaDeviceKind,
  rememberedId?: string,
): DeviceChoice {
  const ofKind = devices.filter((device) => device.kind === kind);
  if (ofKind.length === 0 || ofKind.every((device) => !device.label)) {
    return { label: '', reason: 'unknown' };
  }

  const candidates = safeDevices(devices, kind);
  if (candidates.length === 0) return { label: '', reason: 'none-safe' };

  const remembered = rememberedId
    ? candidates.find((device) => device.deviceId === rememberedId)
    : undefined;
  if (remembered) {
    return { deviceId: remembered.deviceId, label: remembered.label, reason: 'remembered' };
  }

  // Chrome lists the Windows default as an alias entry labelled
  // "Default - <real name>". Follow it to the real device when that is safe.
  const alias = ofKind.find((device) => device.deviceId === 'default');
  if (alias) {
    const name = alias.label.replace(ALIAS_PREFIX, '');
    if (!UNSAFE_AUDIO_DEVICE.test(name)) {
      const real = candidates.find((device) => device.label === name);
      return real
        ? { deviceId: real.deviceId, label: real.label, reason: 'default' }
        // The default is safe but its entry could not be matched by name:
        // leave the choice to the browser, which will open that safe default.
        : { label: name, reason: 'default' };
    }
  }

  return { deviceId: candidates[0].deviceId, label: candidates[0].label, reason: 'first-safe' };
}

export async function listAudioDevices(): Promise<AudioDevice[]> {
  if (!navigator.mediaDevices?.enumerateDevices) return [];
  try {
    return await navigator.mediaDevices.enumerateDevices();
  } catch {
    return [];
  }
}

export function rememberedMicrophone(): string | undefined {
  try {
    return localStorage.getItem(MICROPHONE_KEY) ?? undefined;
  } catch {
    return undefined;
  }
}

export function rememberMicrophone(deviceId: string): void {
  try {
    localStorage.setItem(MICROPHONE_KEY, deviceId);
  } catch {
    // Private browsing or storage disabled: the choice just isn't remembered.
  }
}

/**
 * An AudioContext whose output is never a crash-prone device.
 *
 * Only steps in when the default output itself is unsafe and the browser can
 * route an AudioContext elsewhere (`sinkId`, Chrome 110+). The sink is passed
 * to the constructor so the unsafe default is never opened, not even briefly.
 * In every other case this is exactly `new AudioContext(options)`.
 */
export function createSafeAudioContext(
  options: AudioContextOptions,
  devices: AudioDevice[],
): AudioContext {
  const alias = devices.find((device) => device.kind === 'audiooutput' && device.deviceId === 'default');
  const canRoute = typeof AudioContext !== 'undefined' && 'setSinkId' in AudioContext.prototype;
  if (alias && isUnsafeDevice(alias) && canRoute) {
    const output = chooseDevice(devices, 'audiooutput');
    if (output.deviceId) {
      return new AudioContext({ ...options, sinkId: output.deviceId } as AudioContextOptions);
    }
  }
  return new AudioContext(options);
}
