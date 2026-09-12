"""One ephemeral Codex turn, with live assistant text and bounded cleanup."""
import json
import os
import queue
import signal
import subprocess
import threading
import time


class OCRTimeout(TimeoutError):
    pass


class CodexError(RuntimeError):
    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable


class OCRContentFilterError(CodexError):
    def __init__(self):
        super().__init__('The model provider stopped this corner prediction with its content filter. '
                         'Tuldok cannot accept this response; automatic retries have been stopped.')


def check_content_filter(error):
    # Codex can wrap a filtered response as a retryable stream disconnection.
    # The actual reason is in additionalDetails, not the "Reconnecting" message.
    detail = json.dumps(error).lower()
    if 'content_filter' in detail or 'contentfilter' in detail:
        raise OCRContentFilterError()


def run(image, model, prompt, schema, cwd, on_update, timeout=900, effort='low', progress_timeout=120,
        on_event=None):
    """Return final structured JSON; on_update receives only assistant output.

    Reasoning events are used as activity signals, never exposed as OCR text.
    """
    process = subprocess.Popen(['codex', 'app-server', '--stdio'], cwd=cwd,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                               errors='replace', bufsize=1, start_new_session=True)
    messages = queue.Queue()

    def read_stdout():
        try:
            for line in process.stdout:
                try:
                    messages.put(json.loads(line))
                except ValueError:
                    continue
        finally:
            messages.put(None)

    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout
    request_id = 0
    thread_id = None
    output = {}
    finished = None
    last_progress = None

    def track_progress(raw):
        nonlocal last_progress
        if len(raw.encode('utf-8')) > 128 * 1024:
            raise CodexError('Codex returned an oversized corner response.')
        last_progress = time.monotonic()

    def send(value):
        try:
            process.stdin.write(json.dumps(value) + '\n')
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise CodexError('Codex connection closed unexpectedly.', retryable=True) from exc

    def receive():
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise OCRTimeout(f'Codex exceeded the {timeout:g}-second limit for this capture.')
            if last_progress is not None:
                progress_remaining = progress_timeout - (time.monotonic() - last_progress)
                if progress_remaining <= 0:
                    raise CodexError(f'Codex made no new corner prediction progress for {progress_timeout:g} seconds. '
                                     'Stopped this capture; try another vision model.')
                remaining = min(remaining, progress_remaining)
            try:
                message = messages.get(timeout=min(remaining, .25))
            except queue.Empty:
                continue
            if message is None:
                raise CodexError('Codex exited before finishing the capture. Check your Codex login if this repeats.', retryable=True)
            if on_event is not None:
                on_event(message)
            return message

    def notify(message):
        nonlocal finished
        method = message.get('method', '')
        params = message.get('params') or {}
        if 'id' in message and method:
            send({'id': message['id'], 'error': {'code': -32601, 'message': 'Tuldok only accepts image corner predictions.'}})
            raise CodexError('Codex requested an interactive action instead of returning corners.')
        if thread_id and params.get('threadId') not in (None, thread_id):
            return
        if method == 'item/agentMessage/delta':
            item_id = params['itemId']
            if item_id not in output and len(output) >= 16:
                raise CodexError('Codex returned too many output messages.')
            output[item_id] = output.get(item_id, '') + params['delta']
            track_progress(output[item_id])
            on_update('Finding corners', None)
        elif method == 'item/completed' and params.get('item', {}).get('type') == 'agentMessage':
            item = params['item']
            output[item['id']] = item.get('text', '')
            track_progress(output[item['id']])
        elif method == 'turn/completed':
            finished = params['turn']
        elif method == 'error':
            error = params.get('error') or {}
            check_content_filter(error)
            if params.get('willRetry'):
                on_update('Codex is reconnecting', None)
            else:
                raise CodexError(str(error.get('message') or 'Codex could not identify the corners.')[:400])
        elif method.startswith('item/reasoning/') and not output:
            on_update('Reading the image', None)

    def request(method, params):
        nonlocal request_id
        request_id += 1
        send({'id': request_id, 'method': method, 'params': params})
        while True:
            message = receive()
            if message.get('id') == request_id and 'method' not in message:
                if message.get('error'):
                    check_content_filter(message['error'])
                    raise CodexError(str(message['error'].get('message', 'Codex request failed.'))[:400])
                return message.get('result', {})
            notify(message)

    try:
        on_update('Connecting to Codex', None)
        request('initialize', {'clientInfo': {'name': 'tuldok', 'version': '0.1.0'}})
        send({'method': 'initialized', 'params': {}})
        thread = request('thread/start', {
            'model': model, 'cwd': cwd, 'ephemeral': True, 'sandbox': 'read-only',
            'approvalPolicy': 'never', 'config': {'model_reasoning_effort': effort},
            'developerInstructions': 'Locate book corners in the supplied image. Return only the requested JSON. Do not use tools or request user input.',
        })
        thread_id = thread['thread']['id']
        on_update('Reading the image', None)
        request('turn/start', {
            'threadId': thread_id, 'model': model, 'effort': effort, 'outputSchema': schema,
            'input': [{'type': 'text', 'text': prompt}, {'type': 'localImage', 'path': str(image)}],
        })
        while finished is None:
            notify(receive())
        if finished.get('status') != 'completed':
            check_content_filter(finished.get('error'))
            message = (finished.get('error') or {}).get('message') or 'Codex stopped before completing the capture.'
            raise CodexError(str(message)[:400], retryable=finished.get('status') == 'interrupted')
        # Final items are authoritative; some versions omit them from this notification.
        final = [i.get('text', '') for i in finished.get('items', []) if i.get('type') == 'agentMessage']
        candidates = final or list(output.values())
        for text in reversed(candidates):
            try:
                result = json.loads(text)
                if isinstance(result, dict):
                    return result
            except ValueError:
                continue
        raise CodexError('Codex finished without valid corner JSON. Retry this capture.')
    finally:
        # Terminate the whole child session, including tools, on timeout or completion.
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)
            except ProcessLookupError:
                process.wait(timeout=3)
        process.stdin.close()
        reader.join(timeout=1)
        process.stdout.close()
