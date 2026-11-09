"""The statement grid as a clickable Component v2.

Two things are clickable: the section headers (collapse / expand) and the
% / $ toggle in the change block's header. Each fires its own trigger --
'toggle' and 'mode' -- and statement() reports which one fired.

Three constraints shape this file, all of them properties of the runtime rather
than choices:

1.  SHADOW DOM. The component renders isolated (we never pass isolate_styles,
    so the isolating default applies). Page-level CSS cannot reach inside, which
    is why style.TABLE_CSS ships through the ``css=`` parameter, and why the JS
    writes into the ``.mount`` child -- assigning to parentElement.innerHTML
    would wipe the injected <style> along with the table.
2.  SiS CSP. Streamlit-in-Snowflake forbids external scripts and eval, so the
    HTML, CSS and JS are all inline literals. There are no asset directories and
    nothing is fetched at runtime.
3.  TRANSIENT TRIGGERS. setTriggerValue delivers a value on exactly the script
    run its click caused, then clears. Collapse state therefore cannot live in
    the component -- it lives in st.session_state and is passed back down as
    part of the rendered HTML.

The nonce on the trigger value is deliberate. Collapsing and re-expanding the
same section sends the same section name twice in a row; appending a
monotonically increasing counter guarantees each click is a distinct value, so a
second click can never be swallowed as a duplicate. The counter lives at JS
module scope, which is evaluated once, rather than inside the exported function,
which re-runs on every data change.

SCROLL. Every click reruns the script and the grid's HTML is replaced, which
would snap a horizontally scrolled table back to its left edge -- and the
toggle sits at the far RIGHT (the change block), so every click would lose the
user's place. The exported function therefore carries scrollLeft across the
replacement, from the outgoing table or, if the mount itself was recreated,
from the last scroll position seen (module scope again).

DEGRADATION. The grid is the dashboard; the clicking is a convenience. So a
component that cannot render must not take the page down with it. Two ways that
happens -- a runtime below 1.57 (no st.components.v2 at all) and a runtime where
the component fails to register -- both fall back to a static grid, and the
caller surfaces the reason via unavailable_reason(). Before this fallback
existed, an unregistered component raised StreamlitAPIException straight out of
the script and the entire dashboard rendered nothing.
"""
from __future__ import annotations

import streamlit as st

from style import TABLE_CSS

_SHELL_HTML = '<div class="pnl"><div class="mount"></div></div>'

_JS = """
let clicks = 0;
let lastLeft = 0;
export default function ({ data, setTriggerValue, parentElement }) {
  const mount = parentElement.querySelector('.mount');
  const prev = mount.querySelector('.table-wrap');
  const left = prev ? prev.scrollLeft : lastLeft;
  mount.innerHTML = data.html;

  const wrap = mount.querySelector('.table-wrap');
  if (wrap) {
    wrap.scrollLeft = left;
    lastLeft = wrap.scrollLeft;
    wrap.addEventListener('scroll', () => { lastLeft = wrap.scrollLeft; });
  }

  mount.querySelectorAll('tr.section-hdr[data-sec]').forEach((tr) => {
    tr.addEventListener('click', () => {
      clicks += 1;
      setTriggerValue('toggle', tr.getAttribute('data-sec') + '|' + clicks);
    });
  });
  mount.querySelectorAll('.dmode button[data-mode]').forEach((btn) => {
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      if (btn.disabled || btn.classList.contains('on')) return;
      clicks += 1;
      setTriggerValue('mode', btn.getAttribute('data-mode') + '|' + clicks);
    });
  });
}
"""

#: The triggers _JS fires, in the order statement() checks them.
TRIGGERS: tuple[str, ...] = ("toggle", "mode")

#: True when the runtime has the API at all. Streamlit 1.57 is the floor for
#: st.components.v2; the interpreter on the global PATH here carries 1.48, so
#: this is a real branch and not defensive noise.
HAS_COMPONENTS_V2 = hasattr(st, "components") and hasattr(st.components, "v2")

#: Set once if the component is present but unusable (e.g. not registered in the
#: active runtime, as happens under streamlit.testing's AppTest harness).
#: Latched rather than retried per run, because registration is not transient.
_RENDER_FAILURE: str | None = None

if HAS_COMPONENTS_V2:
    _renderer = st.components.v2.component(
        "pnl_statement", html=_SHELL_HTML, css=TABLE_CSS, js=_JS
    )


def interactive_available() -> bool:
    return HAS_COMPONENTS_V2 and _RENDER_FAILURE is None


def statement(html: str, *, key: str) -> tuple[str, str] | None:
    """Mount the statement grid; return the click that caused this run, if any.

    ``('toggle', 'Revenue')`` for a section header, ``('mode', 'usd')`` for the
    change toggle. Non-None only on the script run caused by a click, so the
    caller updates its own session_state and lets the next run re-render.
    Returns None on the static fallback path, where nothing is clickable.
    """
    global _RENDER_FAILURE

    if interactive_available():
        try:
            res = _renderer(key=key, data={"html": html},
                            on_toggle_change=lambda: None,
                            on_mode_change=lambda: None)
        except Exception as exc:  # noqa: BLE001 -- degrade, never take the page down
            _RENDER_FAILURE = f"{type(exc).__name__}: {exc}"
        else:
            for trigger in TRIGGERS:
                raw = getattr(res, trigger, None)
                if raw:
                    # Strip the click nonce: 'Revenue|7' -> 'Revenue'.
                    value, _, _nonce = str(raw).rpartition("|")
                    return trigger, value or str(raw)
            return None

    _render_static(html)
    return None


def _render_static(html: str) -> None:
    """Degraded path: the grid renders, clicks do not.

    Injects TABLE_CSS into the page instead of the shadow root, because there is
    no shadow root on this path.
    """
    st.html(f"<style>{TABLE_CSS}</style><div class='pnl'>{html}</div>")


def unavailable_reason() -> str | None:
    """Why the grid's clicks are off, or None when they are working."""
    if not HAS_COMPONENTS_V2:
        return (
            f"Section collapse and the % / $ toggle are disabled: this "
            f"interpreter runs Streamlit "
            f"{st.__version__}, and `st.components.v2` needs >= 1.57. Launch via "
            f"`.\\run.ps1` so the project's own .venv is used."
        )
    if _RENDER_FAILURE is not None:
        return (
            f"Section collapse and the % / $ toggle are disabled: the table "
            f"component did not render "
            f"({_RENDER_FAILURE}). The statement below is complete but static."
        )
    return None
