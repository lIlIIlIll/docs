let activeHref = location.href;
function updatePageToc(elem = undefined) {
    let selectedPageTocElem = elem;
    const pagetoc = document.getElementById("pagetoc");

    function getRect(element) {
        return element.getBoundingClientRect();
    }

    function overflowTop(container, element) {
        return getRect(container).top - getRect(element).top;
    }

    function overflowBottom(container, element) {
        return getRect(container).bottom - getRect(element).bottom;
    }

    // We've not selected a heading to highlight, and the URL needs updating
    // so we need to find a heading based on the URL
    if (selectedPageTocElem === undefined && location.href !== activeHref) {
        activeHref = location.href;
        for (const pageTocElement of pagetoc.children) {
            if (pageTocElement.href === activeHref) {
                selectedPageTocElem = pageTocElement;
            }
        }
    }

    // We still don't have a selected heading, let's try and find the most
    // suitable heading based on the scroll position
    if (selectedPageTocElem === undefined) {
        const margin = window.innerHeight / 3;

        const headers = document.getElementsByClassName("header");
        for (let i = 0; i < headers.length; i++) {
            const header = headers[i];
            if (selectedPageTocElem === undefined && getRect(header).top >= 0) {
                if (getRect(header).top < margin) {
                    selectedPageTocElem = header;
                } else {
                    selectedPageTocElem = headers[Math.max(0, i - 1)];
                }
            }
            // a very long last section's heading is over the screen
            if (selectedPageTocElem === undefined && i === headers.length - 1) {
                selectedPageTocElem = header;
            }
        }
    }

    // Remove the active flag from all pagetoc elements
    for (const pageTocElement of pagetoc.children) {
        pageTocElement.classList.remove("active");
    }

    // If we have a selected heading, set it to active and scroll to it
    if (selectedPageTocElem !== undefined) {
        for (const pageTocElement of pagetoc.children) {
            if (selectedPageTocElem.href.localeCompare(pageTocElement.href) === 0) {
                pageTocElement.classList.add("active");
                if (overflowTop(pagetoc, pageTocElement) > 0) {
                    pagetoc.scrollTop = pageTocElement.offsetTop;
                }
                if (overflowBottom(pagetoc, pageTocElement) < 0) {
                    pagetoc.scrollTop -= overflowBottom(pagetoc, pageTocElement);
                }
            }
        }
    }
}

if (document.getElementsByClassName("header").length <= 1) {
    // There's one or less headings, we don't need a page table of contents
    document.getElementById("sidetoc").remove();
} else {
    // Populate sidebar on load
    window.addEventListener("load", () => {
        const pagetoc = document.getElementById("pagetoc");
        const links = [];
        const levels = [];
        const html = document.documentElement;

        function levelFromTag(tagName) {
            const m = /^H(\d+)$/.exec(tagName);
            return m ? parseInt(m[1], 10) : 0;
        }

        function setCollapsed(idx, collapsed) {
            const baseLevel = levels[idx];
            links[idx].classList.toggle("pagetoc-collapsed", collapsed);
            for (let j = idx + 1; j < links.length; j++) {
                if (levels[j] <= baseLevel) {
                    break;
                }
                if (collapsed) {
                    links[j].classList.add("pagetoc-hidden");
                } else {
                    links[j].classList.remove("pagetoc-hidden");
                }
            }
        }

        function expandForActive(idx) {
            const activeLevel = levels[idx];
            if (activeLevel <= 2) {
                return;
            }
            for (let j = idx - 1; j >= 0; j--) {
                if (levels[j] === 2) {
                    setCollapsed(j, false);
                    break;
                }
            }
        }

        for (const header of document.getElementsByClassName("header")) {
            const link = document.createElement("a");
            link.appendChild(document.createTextNode(header.text));
            link.href = header.hash;
            const tagName = header.parentElement.tagName;
            link.classList.add("pagetoc-" + tagName);
            pagetoc.appendChild(link);
            link.onclick = () => {
                updatePageToc(link);
                html.classList.remove("pagetoc-open");
            };

            links.push(link);
            levels.push(levelFromTag(tagName));

            // Add toggle for H2 headings to collapse their children (may be removed if no children)
            if (tagName === "H2") {
                const toggle = document.createElement("span");
                toggle.className = "pagetoc-toggle";
                toggle.textContent = "▸";
                toggle.onclick = (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const idx = links.indexOf(link);
                    if (idx === -1) {
                        return;
                    }
                    const collapsed = !links[idx].classList.contains("pagetoc-collapsed");
                    setCollapsed(idx, collapsed);
                };
                link.prepend(toggle);
            }
        }
        // Remove toggles for H2 headings without children
        for (let i = 0; i < links.length; i++) {
            if (levels[i] !== 2) {
                continue;
            }
            let hasChild = false;
            for (let j = i + 1; j < links.length; j++) {
                if (levels[j] <= 2) {
                    break;
                }
                if (levels[j] > 2) {
                    hasChild = true;
                    break;
                }
            }
            if (!hasChild) {
                links[i].classList.add("pagetoc-no-children");
                const toggle = links[i].querySelector(".pagetoc-toggle");
                if (toggle) {
                    toggle.remove();
                }
                links[i].classList.remove("pagetoc-collapsed");
            }
        }
        updatePageToc();

        // Ensure active section is visible after initial render
        const activeIdx = links.findIndex((link) => link.classList.contains("active"));
        if (activeIdx !== -1) {
            expandForActive(activeIdx);
            const activeLink = links[activeIdx];
            if (activeLink) {
                const top = activeLink.offsetTop - pagetoc.clientHeight / 3;
                pagetoc.scrollTop = Math.max(0, top);
            }
        }

        function ensureMobileControls() {
            if (!pagetoc || document.getElementById("pagetoc-mobile-toggle")) {
                return;
            }
            const btn = document.createElement("button");
            btn.id = "pagetoc-mobile-toggle";
            btn.className = "pagetoc-fab";
            btn.type = "button";
            btn.textContent = "目录";
            btn.setAttribute("aria-controls", "pagetoc");

            const scrim = document.createElement("div");
            scrim.id = "pagetoc-scrim";
            scrim.className = "pagetoc-scrim";

            const toggle = (force) => {
                const next = typeof force === "boolean" ? force : !html.classList.contains("pagetoc-open");
                html.classList.toggle("pagetoc-open", next);
            };

            btn.addEventListener("click", () => toggle(), false);
            scrim.addEventListener("click", () => toggle(false), false);
            window.addEventListener("keydown", (e) => {
                if (e.key === "Escape") {
                    toggle(false);
                }
            }, false);

            document.body.appendChild(scrim);
            document.body.appendChild(btn);
        }

        ensureMobileControls();
    });

    // Update page table of contents selected heading on scroll
    window.addEventListener("scroll", () => {
        updatePageToc();
        const pagetoc = document.getElementById("pagetoc");
        if (!pagetoc) {
            return;
        }
        const items = Array.from(pagetoc.children);
        const activeIdx = items.findIndex((link) => link.classList.contains("active"));
        if (activeIdx !== -1) {
            const activeLink = items[activeIdx];
            const activeLevel = /^pagetoc-H(\d+)$/.exec(
                Array.from(activeLink.classList).find((c) => c.startsWith("pagetoc-H")) || "",
            );
            if (activeLevel && parseInt(activeLevel[1], 10) > 2) {
                // Expand the nearest H2 ancestor if collapsed
                for (let j = activeIdx - 1; j >= 0; j--) {
                    const cls = Array.from(items[j].classList).find((c) => c.startsWith("pagetoc-H"));
                    if (!cls) {
                        continue;
                    }
                    const lvl = parseInt(cls.replace("pagetoc-H", ""), 10);
                    if (lvl === 2) {
                        items[j].classList.remove("pagetoc-collapsed");
                        for (let k = j + 1; k < items.length; k++) {
                            const kcls = Array.from(items[k].classList).find((c) => c.startsWith("pagetoc-H"));
                            if (kcls && parseInt(kcls.replace("pagetoc-H", ""), 10) <= 2) {
                                break;
                            }
                            items[k].classList.remove("pagetoc-hidden");
                        }
                        break;
                    }
                }
            }
        }
        if (document.documentElement.classList.contains("pagetoc-open")) {
            const activeLink = items[activeIdx];
            if (activeLink) {
                const top = activeLink.offsetTop - pagetoc.clientHeight / 3;
                pagetoc.scrollTop = Math.max(0, top);
            }
        }
    });
}
