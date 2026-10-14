'use strict';
// Audio owns display/playback and timed fields; Workbench owns save/review/navigation.
let audioSegments = [], audioPending = false, audioGeneration = 0, audioController = null;
let audioContext = null, audioSource = null, audioInspection = null, audioEditingIndex = null, audioPlaybackGeneration = 0;
function audioStop() {
  ++audioPlaybackGeneration;
  if (audioSource) { audioSource.onended = null; try { audioSource.stop(); } catch {} audioSource.disconnect(); audioSource = null; }
  $('audio-player').pause();
}
function audioDispose() {
  ++audioGeneration; audioController?.abort(); audioController = null; audioStop();
  const context = audioContext; audioContext = null;
  if (context) context.close().catch(() => {});
}
function audioDraw() {
  const svg = $('audio-waveform'); svg.replaceChildren();
  if (!audioInspection) return;
  const channel = Number($('audio-channel').value), peaks = audioInspection.peaks[channel];
  const ns = 'http://www.w3.org/2000/svg', graph = document.createElementNS(ns, 'path');
  graph.setAttribute('d', peaks.map((peak, i) => `M${i * 600 / peaks.length},${48 - peak * 44}v${peak * 88}`).join(' '));
  graph.setAttribute('stroke', '#4168db'); graph.setAttribute('stroke-width', '1'); svg.append(graph);
  svg.setAttribute('aria-label', `Peak waveform for source channel ${channel + 1}; timing is entered in source frames below`);
}
function audioResetFields() {
  audioEditingIndex = null; audioPending = false;
  $('audio-start').value = 0; $('audio-end').value = current?.audio?.frame_count || 1;
  for (const key of ['transcript', 'label', 'speaker']) $('audio-' + key).value = '';
  $('audio-add').textContent = 'Add interval'; audioTimeHint();
}
function audioTimeHint() {
  if (!current?.audio) return;
  const rate = current.audio.sample_rate_hz;
  $('audio-time-hint').textContent = `${(Number($('audio-start').value) / rate).toFixed(5)}–${(Number($('audio-end').value) / rate).toFixed(5)} seconds · end frame excluded. Source frames remain authoritative.`;
}
function audioSegmentFields() {
  const segment = {start_frame:Number($('audio-start').value), end_frame:Number($('audio-end').value), channel:Number($('audio-channel').value),
    transcript:$('audio-transcript').value.trim(), label:$('audio-label').value.trim(), speaker:$('audio-speaker').value.trim()};
  if (![segment.start_frame, segment.end_frame, segment.channel].every(Number.isSafeInteger) || segment.start_frame < 0 || segment.end_frame <= segment.start_frame || segment.end_frame > current.audio.frame_count || segment.channel < 0 || segment.channel >= current.audio.channels)
    throw Error('Use source-frame integers: 0 ≤ start < end ≤ frame count, and an available channel.');
  return segment;
}
function audioAnnotation() {
  if (audioPending) throw Error('Add or update the interval, or clear its fields, before saving the record.');
  return {segments:structuredClone(audioSegments)};
}
function audioRenderSegments() {
  $('audio-segments').replaceChildren();
  audioSegments.forEach((segment, index) => {
    const item = document.createElement('li'), text = document.createElement('p');
    text.textContent = `Channel ${segment.channel + 1} · [${segment.start_frame}, ${segment.end_frame}) · ${[segment.label, segment.transcript].filter(Boolean).join(' · ')}${segment.speaker ? ' · ' + segment.speaker : ''}`;
    const edit = document.createElement('button'); edit.type = 'button'; edit.textContent = 'Edit'; edit.setAttribute('aria-label', `Edit audio interval ${index + 1}`);
    edit.onclick = () => {
      if (audioPending) { notice('Add/update or clear current interval fields first.', true); return; }
      audioEditingIndex = index;
      for (const [field, key] of [['start','start_frame'],['end','end_frame'],['channel','channel'],['transcript','transcript'],['label','label'],['speaker','speaker']]) $('audio-' + field).value = segment[key];
      $('audio-add').textContent = 'Update interval'; audioTimeHint(); audioDraw(); $('audio-start').focus();
    };
    const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Remove'; remove.setAttribute('aria-label', `Remove audio interval ${index + 1}`);
    remove.onclick = () => {
      if (audioPending) { notice('Add/update or clear current interval fields first.', true); return; }
      audioSegments.splice(index, 1); audioResetFields(); markDirty(); audioRenderSegments(); $('audio-add').focus();
    };
    item.append(text, edit, remove); $('audio-segments').append(item);
  });
  $('audio-empty').hidden = audioSegments.length > 0;
}
function decodeAudioInspection(value, record) {
  if (!value || Object.keys(value).sort().join() !== 'bins,channels,content_hash,frame_count,id,peaks,sample_rate_hz' || value.id !== record.id || value.content_hash !== record.content_hash ||
      value.frame_count !== record.audio.frame_count || value.channels !== record.audio.channels || value.sample_rate_hz !== record.audio.sample_rate_hz || value.bins !== Math.min(600, value.frame_count) ||
      !Array.isArray(value.peaks) || value.peaks.length !== value.channels || !value.peaks.every(channel => Array.isArray(channel) && channel.length === value.bins && channel.every(peak => typeof peak === 'number' && Number.isFinite(peak) && peak >= 0 && peak <= 1)))
    throw Error('Invalid audio waveform response. Original playback and saved annotations remain separate.');
  return value;
}
function audioShown(record) {
  audioDispose(); audioInspection = null; audioSegments = []; audioPending = false;
  $('audio-inspection').hidden = record.kind !== 'audio'; $('audio-player').removeAttribute('src'); $('audio-player').load();
  $('audio-waveform').replaceChildren(); $('audio-status').textContent = '';
  // Hidden controls still participate in the parent form's native validity checks.
  for (const id of ['audio-start','audio-end']) $(id).removeAttribute('max');
  audioResetFields(); $('audio-channel').replaceChildren();
  if (record.kind !== 'audio') return;
  const meta = record.audio;
  $('audio-metadata').textContent = `${meta.duration_seconds.toFixed(3)} s · ${meta.sample_rate_hz.toLocaleString()} Hz · ${meta.channels} ${meta.channels === 1 ? 'channel' : 'channels'} · ${meta.frame_count.toLocaleString()} frames · PCM 16-bit`;
  $('audio-player').src = '/api/workbench/asset/' + record.id;
  $('audio-download').href = $('audio-player').src; $('audio-download').download = record.name;
  $('audio-channel').replaceChildren();
  for (let channel = 0; channel < meta.channels; channel++) { const option = document.createElement('option'); option.value = channel; option.textContent = `Channel ${channel + 1} (index ${channel})`; $('audio-channel').append(option); }
  for (const id of ['audio-start', 'audio-end']) $(id).max = meta.frame_count;
  audioSegments = structuredClone(record.annotation?.segments || []); audioResetFields(); audioRenderSegments();
  const generation = audioGeneration, controller = new AbortController(); audioController = controller;
  const owns = () => audioGeneration === generation && current?.id === record.id;
  $('audio-status').textContent = 'Loading source-channel waveform…';
  (async () => {
    try {
      const response = await (globalThis.TuldokAuth?.fetch || fetch)('/api/workbench/audio-inspection/' + record.id, {signal:controller.signal}), raw = await response.json();
      if (!response.ok) throw Error(raw.error || 'Audio inspection unavailable.');
      const value = decodeAudioInspection(raw, record); if (!owns()) return;
      audioInspection = value; audioDraw(); $('audio-status').textContent = 'Original bytes retained. Waveform peaks summarize source frames; no transcript is inferred.';
    } catch (error) { if (owns() && error.name !== 'AbortError') $('audio-status').textContent = error.message; }
    finally { if (audioController === controller) audioController = null; }
  })();
}
for (const id of ['audio-start','audio-end','audio-transcript','audio-label','audio-speaker']) $(id).addEventListener('input', () => { audioPending = true; audioTimeHint(); });
$('audio-channel').addEventListener('change', () => { audioPending = true; audioDraw(); });
action('audio-add', () => {
  const segment = audioSegmentFields();
  if (!segment.transcript && !segment.label) throw Error('Enter a human transcript or class label for this interval.');
  if (audioEditingIndex === null) {
    if (audioSegments.length >= 200) throw Error('At most 200 timed intervals per record.');
    audioSegments.push(segment);
  } else audioSegments[audioEditingIndex] = segment;
  audioResetFields(); markDirty(); audioRenderSegments(); notice('Interval added to the unsaved draft. Save and explicitly review when ready.');
});
action('audio-clear-fields', () => { audioResetFields(); notice('Interval fields cleared. Saved and added intervals remain.'); });
action('audio-stop', () => { audioStop(); $('audio-status').textContent = 'Playback paused.'; });
action('audio-play-interval', async () => {
  const record = current, segment = audioSegmentFields(), generation = audioGeneration;
  audioStop(); const playback = audioPlaybackGeneration; $('audio-status').textContent = 'Preparing source-channel interval playback…';
  const context = audioContext || new AudioContext({sampleRate:record.audio.sample_rate_hz}); audioContext = context;
  try {
  await context.resume();
  const response = await (globalThis.TuldokAuth?.fetch || fetch)('/api/workbench/asset/' + record.id);
  if (!response.ok) throw Error('Original audio unavailable.');
  const buffer = await context.decodeAudioData(await response.arrayBuffer());
  if (generation !== audioGeneration || playback !== audioPlaybackGeneration) return;
  if (buffer.sampleRate !== record.audio.sample_rate_hz || buffer.length !== record.audio.frame_count || buffer.numberOfChannels !== record.audio.channels)
    throw Error('Browser cannot preserve the source sample rate/frame count for interval playback. Use the original player; annotation timing remains source frames.');
  const selected = context.createBuffer(1, segment.end_frame - segment.start_frame, buffer.sampleRate);
  selected.copyToChannel(buffer.getChannelData(segment.channel).subarray(segment.start_frame, segment.end_frame), 0);
  const source = context.createBufferSource(); audioSource = source; source.buffer = selected; source.connect(context.destination);
  source.onended = () => { source.disconnect(); if (audioSource === source) { audioSource = null; $('audio-status').textContent = 'Selected interval playback finished.'; } };
  source.start(); $('audio-status').textContent = `Playing channel ${segment.channel + 1}, source frames [${segment.start_frame}, ${segment.end_frame}).`;
  } catch (error) {
    if (generation === audioGeneration && playback === audioPlaybackGeneration) throw error;
  }
});
$('audio-player').addEventListener('error', () => { if (current?.kind === 'audio' && $('audio-player').getAttribute('src')) $('audio-status').textContent = 'Original WAV playback unavailable. Restore missing source bytes or use a supported browser.'; });
window.addEventListener('pagehide', audioDispose);
action('audio-import-form', async () => {
  const file = $('audio-file').files[0];
  if (!file || !file.size || file.size > 8 * 1024 * 1024) throw Error('Choose a PCM WAV file, at most 8 MiB.');
  const status = $('audio-import-status'); status.textContent = 'Reading and validating original WAV…';
  try {
    const raw = new Uint8Array(await file.arrayBuffer()); let binary = '';
    for (let start = 0; start < raw.length; start += 32768) binary += String.fromCharCode(...raw.subarray(start, start + 32768));
    const group = $('audio-group').value.trim();
    const record = await api('audio-import', {wav:btoa(binary), name:file.name, groups:group ? [group] : [], rights:$('audio-rights').value || 'unknown'});
    status.textContent = `Imported ${record.name}, unreviewed. Open it in the collection to play and annotate.`;
    await refresh();
  } catch (error) { status.textContent = error.message + ' Check the collection before repeating a request whose response was lost.'; throw error; }
}, 'submit');
