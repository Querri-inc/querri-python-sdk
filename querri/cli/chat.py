"""querri chat — top-level conversational command.

Sends a prompt to the active project's chat, auto-creating the chat
if one doesn't exist yet. Designed for quick, stateful interaction:

    querri project select "Sales Analysis"
    querri chat "what trends do you see?"
    querri chat "break it down by region"
"""

from __future__ import annotations

import os
import re
import signal
import sys
from typing import Optional

import typer

from querri.cli._context import (
    get_client,
    resolve_project_id,
    resolve_user_id,
    _get_profile,
    _save_profile,
)
from querri.cli._output import (
    EXIT_SUCCESS,
    handle_api_error,
    print_error,
    print_json,
    print_success,
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Strip HTML tags from a string."""
    return _HTML_TAG_RE.sub("", text).strip()


chat_app = typer.Typer(
    name="chat",
    help="Send a prompt to the active project's chat.",
    invoke_without_command=True,
    rich_markup_mode="rich",
)


@chat_app.callback(invoke_without_command=True)
def chat_command(
    ctx: typer.Context,
    prompt: Optional[str] = typer.Argument(None, help="Message to send."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model selection."),
    new: bool = typer.Option(False, "--new", help="Force a new chat session."),
    reasoning: bool = typer.Option(False, "--reasoning", "-r", help="Show reasoning traces."),
) -> None:
    """Send a prompt to the active project's chat.

    Auto-creates a chat if none is active. Use --new to start a fresh
    conversation.

    Examples:
        querri chat "summarize the data"
        querri chat "show me Q4 revenue" --model gpt-4o
        querri chat "start over with a new analysis" --new
    """
    if ctx.invoked_subcommand is not None:
        return
    if prompt is None:
        # No prompt given — show help
        ctx.get_help()
        return
    # Typer's invoke_without_command=True grabs subcommand names as the
    # positional prompt argument. Detect and forward to the subcommand.
    _subcommand_names = {cmd.name for cmd in chat_app.registered_commands if cmd.callback}
    if prompt in _subcommand_names:
        if prompt == "show":
            chat_show(ctx, chat_id=None)
        return

    obj = ctx.ensure_object(dict)
    is_json = obj.get("json", False)
    is_interactive = obj.get("interactive", False)

    project_id = resolve_project_id(ctx)
    user_id = resolve_user_id(ctx)
    client = get_client(ctx)

    # Resolve or create chat
    chat_id = obj.get("chat")  # explicit --chat flag

    if not chat_id and not new:
        # Check stored active chat
        profile = _get_profile(ctx)
        if profile and profile.active_chat_id and profile.active_project_id == project_id:
            chat_id = profile.active_chat_id

    if not chat_id or new:
        # Create a new chat
        try:
            chat = client.projects.chats.create(project_id)
            chat_id = chat.id
        except Exception as exc:
            raise typer.Exit(code=handle_api_error(exc, is_json=is_json))

        if not is_json and not obj.get("quiet"):
            print(f"  New chat: {chat_id}", file=sys.stderr)

    # Save active chat
    profile = _get_profile(ctx)
    if profile:
        profile.active_chat_id = chat_id
        _save_profile(ctx, profile)

    # Stream the response
    try:
        stream = client.projects.chats.stream(
            project_id,
            chat_id,
            prompt=prompt,
            user_id=user_id,
            model=model,
        )
    except Exception as exc:
        raise typer.Exit(code=handle_api_error(exc, is_json=is_json))

    # Set up Ctrl+C handler
    cancelled = False

    def _sigint_handler(signum: int, frame: object) -> None:
        nonlocal cancelled
        cancelled = True
        stream._signal_cancel()

    old_handler = signal.signal(signal.SIGINT, _sigint_handler)

    try:
        if is_json:
            _stream_json(stream)
        elif is_interactive:
            _stream_rich(stream, show_reasoning=reasoning)
        else:
            _stream_plain(stream, show_reasoning=reasoning)
    except Exception as exc:
        if not cancelled:
            raise typer.Exit(code=handle_api_error(exc, is_json=is_json))
    finally:
        signal.signal(signal.SIGINT, old_handler)

    if cancelled:
        print_error("Stream cancelled.")
        raise typer.Exit(code=EXIT_SUCCESS)


# ---------------------------------------------------------------------------
# Streaming renderers (shared with chats.py)
# ---------------------------------------------------------------------------


def _stream_plain(stream: object, *, show_reasoning: bool = False) -> None:
    from querri._streaming import ChatStream
    assert isinstance(stream, ChatStream)

    # Debug: dump raw lines first to diagnose parsing
    if os.environ.get("QUERRI_DEBUG_STREAM"):
        for line in stream._response.iter_lines():
            print(f"[RAW] {line!r}", file=sys.stderr)
        stream._response.close()
        return

    in_reasoning = False

    for event in stream.events():
        if event.event_type == "reasoning-start":
            in_reasoning = True
            if show_reasoning:
                print("\n--- Reasoning ---", file=sys.stderr)
        elif event.event_type == "reasoning-delta" and event.reasoning_text:
            if show_reasoning:
                print(event.reasoning_text, end="", flush=True, file=sys.stderr)
        elif event.event_type == "reasoning-end":
            in_reasoning = False
            if show_reasoning:
                print("\n-----------------\n", file=sys.stderr)
        elif event.event_type == "text-delta" and event.text:
            print(event.text, end="", flush=True)
        elif event.event_type == "tool-output-available":
            name = event.tool_name or "unknown"
            print(f"\n[Step: {name}]", file=sys.stderr)
            if event.tool_data and isinstance(event.tool_data, dict):
                _print_tool_preview_plain(event.tool_data)
        elif event.event_type == "file":
            url = event.file_url or ""
            media = event.media_type or ""
            if "image" in media:
                from querri.cli._image import download_image
                path = download_image(url)
                if path:
                    print(f"\n  Chart saved: {path}", file=sys.stderr)
                print(f"  Open chart: {url}", file=sys.stderr)
            else:
                print(f"\n  Open file: {url}", file=sys.stderr)
        elif event.event_type == "terminate":
            reason = event.terminate_reason or "unknown"
            msg = event.terminate_message or ""
            print(f"\nStream closed: {reason}. {msg}", file=sys.stderr)
        elif event.event_type == "error":
            print(f"\nError: {event.error}", file=sys.stderr)
    print()


def _print_tool_preview_plain(data: dict) -> None:
    """Print a compact table preview for tool output in plain mode."""
    rows = data.get("rows") or data.get("data") or data.get("results")
    title = data.get("title") or data.get("name") or ""
    if not isinstance(rows, list) or not rows:
        return
    cols = list(rows[0].keys()) if isinstance(rows[0], dict) else []
    n_rows = len(rows)
    n_cols = len(cols)
    if title:
        print(f"  {title}", file=sys.stderr)
    print(f"  {n_cols} columns, {n_rows} rows", file=sys.stderr)
    # Show first 3 rows
    preview = rows[:3]
    if cols:
        header = " | ".join(f"{c:>12}" for c in cols[:5])
        print(f"  {header}", file=sys.stderr)
        for row in preview:
            vals = [str(row.get(c, ""))[:12] for c in cols[:5]]
            print(f"  {' | '.join(f'{v:>12}' for v in vals)}", file=sys.stderr)
        if n_rows > 3:
            print(f"  ... and {n_rows - 3} more rows", file=sys.stderr)


def _stream_rich(stream: object, *, show_reasoning: bool = False) -> None:
    from rich.console import Console, Group
    from rich.live import Live
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    from querri._streaming import ChatStream
    assert isinstance(stream, ChatStream)

    console = Console()
    reasoning_text = ""
    response_text = ""
    tool_panels: list[Panel | Table] = []
    file_links: list[str] = []

    def _build_display() -> Group:
        parts: list[object] = []
        # Reasoning panel
        if reasoning_text and show_reasoning:
            r_text = Text(reasoning_text, style="dim italic")
            parts.append(Panel(
                r_text,
                title="[dim]Reasoning[/dim]",
                title_align="left",
                border_style="dim",
                padding=(0, 1),
            ))
        elif reasoning_text and not show_reasoning:
            # Show a one-line collapsed indicator
            lines = reasoning_text.strip().count("\n") + 1
            parts.append(Text(
                f"  Reasoning ({lines} lines) — rerun with --reasoning to expand",
                style="dim",
            ))
        # Tool result previews
        for panel in tool_panels:
            parts.append(panel)
        # File/image links
        for link in file_links:
            parts.append(link)
        # Response markdown
        if response_text:
            parts.append(Markdown(response_text))
        return Group(*parts) if parts else Group(Text(""))

    with Live(Text(""), console=console, refresh_per_second=10) as live:
        for event in stream.events():
            if event.event_type == "reasoning-start":
                pass  # Will show when first delta arrives
            elif event.event_type == "reasoning-delta" and event.reasoning_text:
                reasoning_text += event.reasoning_text
                live.update(_build_display())
            elif event.event_type == "reasoning-end":
                live.update(_build_display())
            elif event.event_type == "text-delta" and event.text:
                response_text += event.text
                live.update(_build_display())
            elif event.event_type == "tool-output-available":
                panel = _build_tool_panel(event.tool_name, event.tool_data)
                if panel is not None:
                    tool_panels.append(panel)
                    live.update(_build_display())
            elif event.event_type == "file":
                url = event.file_url or ""
                media = event.media_type or ""
                if "image" in media:
                    from querri.cli._image import render_image_rich
                    # Get terminal width for sizing
                    img_width = min(console.width - 4, 70)
                    renderable = render_image_rich(
                        url,
                        caption=event.raw_data or "",
                        max_width=img_width,
                        max_height=24,
                    )
                    file_links.append(renderable)
                else:
                    link = Text.from_markup(
                        f"  [link={url}][bold #f15a24]📎 Open file[/bold #f15a24][/link]"
                        f"  [dim]{url}[/dim]"
                    )
                    file_links.append(link)
                live.update(_build_display())
            elif event.event_type == "terminate":
                reason = event.terminate_reason or "unknown"
                msg = event.terminate_message or "Start a new chat to continue."
                console.print(f"\n[#f15a24]Stream closed: {reason}. {msg}[/#f15a24]")
            elif event.event_type == "error":
                console.print(f"\n[red]Error: {event.error}[/red]")


def _build_tool_panel(
    tool_name: str | None,
    tool_data: object | None,
) -> object | None:
    """Build a Rich Panel with a compact table preview for a tool result."""
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    name = tool_name or "Result"

    if not isinstance(tool_data, dict):
        return Panel(
            Text(f"Step completed", style="dim"),
            title=f"[bold #f15a24]{name}[/bold #f15a24]",
            title_align="left",
            border_style="#f15a24",
            padding=(0, 1),
        )

    rows = tool_data.get("rows") or tool_data.get("data") or tool_data.get("results")
    title = tool_data.get("title") or tool_data.get("name") or name

    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        # Non-tabular tool output — show summary
        summary = tool_data.get("summary") or tool_data.get("message") or ""
        if summary:
            return Panel(
                Text(str(summary)),
                title=f"[bold #f15a24]{title}[/bold #f15a24]",
                title_align="left",
                border_style="#f15a24",
                padding=(0, 1),
            )
        return Panel(
            Text("Step completed", style="dim"),
            title=f"[bold #f15a24]{title}[/bold #f15a24]",
            title_align="left",
            border_style="#f15a24",
            padding=(0, 1),
        )

    # Tabular data — build a compact Rich table preview
    cols = list(rows[0].keys())
    n_rows = len(rows)
    n_cols = len(cols)
    show_cols = cols[:6]  # Max 6 columns in preview

    table = Table(
        title=f"[bold #f15a24]{title}[/bold #f15a24]",
        caption=f"{n_rows} rows × {n_cols} columns",
        caption_style="dim",
        show_header=True,
        header_style="bold",
        border_style="#f15a24",
        padding=(0, 1),
        expand=False,
    )
    for col in show_cols:
        table.add_column(col)
    if n_cols > 6:
        table.add_column("…", style="dim")

    # Show first 5 rows
    for row in rows[:5]:
        vals = [str(row.get(c, ""))[:20] for c in show_cols]
        if n_cols > 6:
            vals.append("…")
        table.add_row(*vals)
    if n_rows > 5:
        placeholder = ["…"] * len(show_cols)
        if n_cols > 6:
            placeholder.append("")
        table.add_row(*placeholder, style="dim")

    return table


def _stream_json(stream: object) -> None:
    from querri._streaming import ChatStream
    assert isinstance(stream, ChatStream)

    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[dict] = []
    files: list[dict] = []
    usage: dict | None = None

    for event in stream.events():
        if event.event_type == "text-delta" and event.text:
            text_parts.append(event.text)
        elif event.event_type == "reasoning-delta" and event.reasoning_text:
            reasoning_parts.append(event.reasoning_text)
        elif event.event_type == "tool-output-available":
            tool_calls.append({"tool_name": event.tool_name, "output": event.tool_data})
        elif event.event_type == "file":
            files.append({"url": event.file_url, "media_type": event.media_type})
        elif event.event_type == "finish":
            usage = event.usage
        elif event.event_type == "terminate":
            text_parts.append(f"\n[Stream closed: {event.terminate_reason}]")

    result: dict = {
        "message_id": stream.message_id,
        "text": "".join(text_parts),
        "tool_calls": tool_calls,
        "files": files,
    }
    if reasoning_parts:
        result["reasoning"] = "".join(reasoning_parts)
    if usage:
        result["usage"] = usage

    print_json(result)


# ---------------------------------------------------------------------------
# querri chat show
# ---------------------------------------------------------------------------


@chat_app.command("show")
def chat_show(
    ctx: typer.Context,
    chat_id: Optional[str] = typer.Argument(None, help="Chat ID (default: active chat)."),
) -> None:
    """Show the conversation history for a chat.

    Displays all messages in the active (or specified) chat with Rich
    formatting. User messages appear right-aligned, assistant messages
    left-aligned with markdown rendering.

    Example: querri chat show
    """
    obj = ctx.ensure_object(dict)
    is_json = obj.get("json", False)
    is_interactive = obj.get("interactive", False)

    project_id = resolve_project_id(ctx)
    client = get_client(ctx)

    # Resolve chat ID
    cid = chat_id or obj.get("chat")
    if not cid:
        profile = _get_profile(ctx)
        if profile and profile.active_chat_id and profile.active_project_id == project_id:
            cid = profile.active_chat_id

    if not cid:
        print_error("No active chat. Send a message first with: querri chat \"hello\"")
        raise typer.Exit(code=1)

    # Fetch chat messages from internal API
    chat_raw = _fetch_chat_internal(client, project_id, cid)

    # Fetch full project for step figures
    from querri.cli.projects import _get_full_project
    full_project = _get_full_project(client, project_id)

    # Fallback to v1 API for chat if internal failed
    chat = None
    if chat_raw is None:
        try:
            chat = client.projects.chats.get(project_id, cid)
        except Exception as exc:
            raise typer.Exit(code=handle_api_error(exc, is_json=is_json))

    if is_json:
        print_json(chat_raw or chat)
        return

    # Build messages list
    messages: list = []
    if chat_raw and "messages" in chat_raw:
        from querri.types.chat import Message
        for m in chat_raw["messages"]:
            if isinstance(m, dict):
                try:
                    messages.append(Message.model_validate(m))
                except Exception:
                    pass
    elif chat:
        messages = getattr(chat, "messages", None) or []

    steps = getattr(full_project, "steps", None) or [] if full_project else []

    if not messages and not steps:
        print_error("Chat has no messages.")
        raise typer.Exit(code=EXIT_SUCCESS)

    # Build a lightweight chat object for rendering
    if chat is None:
        from types import SimpleNamespace
        chat = SimpleNamespace(
            id=cid,
            name=chat_raw.get("name", "") if chat_raw else "",
        )

    if is_interactive:
        _render_chat_rich(chat, messages, steps, client, project_id=project_id)
    else:
        _render_chat_plain(chat, messages, steps, client)


def _fetch_chat_internal(client: object, project_id: str, chat_id: str) -> dict | None:
    """Fetch chat with messages from the internal ``/api/`` endpoint."""
    try:
        import httpx as _httpx
        http = client._http  # type: ignore[attr-defined]
        base_url = str(http._client.base_url)
        internal_base = base_url.replace("/api/v1", "/api")
        resp = _httpx.get(
            f"{internal_base}/projects/{project_id}/chat/{chat_id}",
            headers=dict(http._client.headers),
            follow_redirects=True,
            timeout=30.0,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def _render_chat_rich(
    chat: object,
    messages: list,
    steps: list | None = None,
    client: object | None = None,
    project_id: str = "",
) -> None:
    """Render chat history with Rich panels and ASCII art charts."""
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.text import Text

    from querri.cli._output import QUERRI_ORANGE

    console = Console()

    # Chat header
    name = getattr(chat, "name", "") or "Untitled Chat"
    msg_count = len(messages)
    console.print(Panel(
        Text.from_markup(
            f"[bold {QUERRI_ORANGE}]{name}[/bold {QUERRI_ORANGE}]"
            f"  [dim]{chat.id}[/dim]"
            f"\n[dim]{msg_count} messages[/dim]"
        ),
        border_style=QUERRI_ORANGE,
        padding=(0, 2),
    ))

    for msg in messages:
        role = msg.role
        content = msg.content or ""
        ts = msg.created_at or ""

        if role == "user":
            console.print(Panel(
                Text(content),
                title="[bold]You[/bold]",
                title_align="right",
                subtitle=f"[dim]{ts}[/dim]" if ts else None,
                subtitle_align="right",
                border_style="blue",
                padding=(0, 1),
                width=min(console.width - 10, 80),
            ), justify="right")
        else:
            # Assistant messages render as markdown
            console.print(Panel(
                Markdown(content) if content.strip() else Text("[dim]Empty response[/dim]"),
                title=f"[bold {QUERRI_ORANGE}]Querri[/bold {QUERRI_ORANGE}]",
                title_align="left",
                subtitle=f"[dim]{ts}[/dim]" if ts else None,
                subtitle_align="left",
                border_style=QUERRI_ORANGE,
                padding=(0, 1),
            ))

    # Render step results with ASCII art charts
    if steps:
        _render_step_figures(console, steps, client, project_id=project_id)

    console.print()


def _fetch_step_data_preview(
    step_id: str,
    project_id: str,
    base_url: str,
    auth_headers: dict[str, str],
    limit: int = 5,
) -> list[dict] | None:
    """Fetch the first few rows of step data from the internal API."""
    try:
        import httpx as _httpx
        url = f"{base_url}/api/projects/{project_id}/steps/{step_id}/data"
        resp = _httpx.get(
            url,
            params={"page": 1, "page_size": limit},
            headers=auth_headers,
            follow_redirects=True,
            timeout=10.0,
        )
        if resp.status_code == 200:
            return resp.json().get("data", [])
    except Exception:
        pass
    return None


def _build_data_step_content(
    step: object,
    project_id: str,
    base_url: str,
    auth_headers: dict[str, str],
) -> object:
    """Build Rich content for a data step: message + table preview + view command."""
    from rich.console import Group
    from rich.table import Table
    from rich.text import Text

    parts: list[object] = []

    # Step message
    msg = _strip_html(getattr(step, "message", None) or "")
    if msg:
        parts.append(Text(msg, style="italic"))

    # Metadata line
    num_rows = getattr(step, "num_rows", None)
    num_cols = getattr(step, "num_cols", None)
    headers = getattr(step, "headers", None) or []
    if num_rows is not None:
        meta = f"{num_rows} rows × {num_cols or len(headers)} columns"
        parts.append(Text(meta, style="dim"))

    rows = _fetch_step_data_preview(
        step.id,
        project_id,
        base_url,
        auth_headers,
    )

    if rows and isinstance(rows, list) and rows:
        cols = list(rows[0].keys()) if isinstance(rows[0], dict) else []
        show_cols = cols[:6]

        table = Table(
            show_header=True,
            header_style="bold",
            border_style="dim",
            padding=(0, 1),
            expand=False,
        )
        for col in show_cols:
            table.add_column(col)
        if len(cols) > 6:
            table.add_column("…", style="dim")

        for row in rows[:5]:
            vals = [str(row.get(c, ""))[:20] for c in show_cols]
            if len(cols) > 6:
                vals.append("…")
            table.add_row(*vals)

        if num_rows and num_rows > 5:
            placeholder = ["…"] * len(show_cols)
            if len(cols) > 6:
                placeholder.append("")
            table.add_row(*placeholder, style="dim")

        parts.append(table)

    # Command hint to view full data
    parts.append(Text.from_markup(
        f"\n[dim]querri step data {step.id}[/dim]"
    ))

    return Group(*parts) if parts else Text("[dim]No data[/dim]")


def _render_step_figures(
    console: object,
    steps: list,
    client: object | None = None,
    project_id: str = "",
) -> None:
    """Render step results — data tables and ASCII art charts."""
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    from querri.cli._image import render_image_rich
    from querri.cli._output import QUERRI_ORANGE

    # Resolve the base URL and auth headers for figure downloads
    base_url = ""
    auth_headers: dict[str, str] = {}
    if client:
        try:
            http = client._http
            base_url = str(http._client.base_url).replace("/api/v1", "").rstrip("/")
            auth_headers = {
                k: v for k, v in http._client.headers.items()
                if k.lower() in ("authorization",)
            }
        except Exception:
            pass

    figure_steps = [s for s in steps if s.has_figure and getattr(s, "figure_url", None)]
    data_steps = [s for s in steps if s.has_data and not s.has_figure]

    if not figure_steps and not data_steps:
        return

    console.print()
    console.print(Text("Step Results", style=f"bold {QUERRI_ORANGE}"))

    # Show data steps with table preview
    for step in data_steps:
        content = _build_data_step_content(step, project_id, base_url, auth_headers)
        console.print(Panel(
            content,
            title=f"[bold {QUERRI_ORANGE}]🔍 {step.name}[/bold {QUERRI_ORANGE}]",
            title_align="left",
            border_style="dim",
            padding=(0, 1),
        ))

    # Show figure steps with ASCII art
    for step in figure_steps:
        fig_url = step.figure_url
        # Resolve relative figure paths via /api/files/stream/ endpoint
        if fig_url and not fig_url.startswith("http"):
            fig_url = f"{base_url}/api/files/stream/{fig_url.lstrip('/')}"

        msg = _strip_html(getattr(step, "message", None) or "")
        img_width = min(console.width - 4, 70)
        renderable = render_image_rich(
            fig_url,
            caption=msg,
            max_width=img_width,
            max_height=24,
            headers=auth_headers,
        )

        console.print(Panel(
            renderable,
            title=f"[bold {QUERRI_ORANGE}]📊 {step.name}[/bold {QUERRI_ORANGE}]",
            title_align="left",
            border_style="dim",
            padding=(0, 1),
        ))


def _render_chat_plain(
    chat: object,
    messages: list,
    steps: list | None = None,
    client: object | None = None,
) -> None:
    """Render chat history as plain text."""
    name = getattr(chat, "name", "") or "Untitled Chat"
    print(f"Chat: {name} ({chat.id})")
    print(f"Messages: {len(messages)}")
    print("-" * 40)

    for msg in messages:
        role = msg.role.upper()
        content = msg.content or ""
        ts = msg.created_at or ""
        print(f"\n[{role}] {ts}")
        print(content)

    # Show figures
    if steps:
        base_url = ""
        if client:
            try:
                base_url = str(client._http._client.base_url).replace("/api/v1", "")
            except Exception:
                pass
        figure_steps = [s for s in steps if s.has_figure and getattr(s, "figure_url", None)]
        if figure_steps:
            print("\n--- Charts ---")
            for step in figure_steps:
                fig_url = step.figure_url
                if fig_url and not fig_url.startswith("http"):
                    fig_url = f"{base_url}/api/files/stream/{fig_url.lstrip('/')}"
                msg = _strip_html(getattr(step, "message", None) or "")
                print(f"\n  {step.name}")
                if msg:
                    print(f"  {msg}")
                from querri.cli._image import download_image
                path = download_image(fig_url)
                if path:
                    print(f"  Saved: {path}")
                print(f"  Open: {fig_url}")
    print()
