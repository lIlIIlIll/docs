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
            link.onclick = () => updatePageToc(link);

            links.push(link);
            levels.push(levelFromTag(tagName));

            // Add toggle for H2 headings to collapse their children
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
        updatePageToc();

        // Ensure active section is visible after initial render
        const activeIdx = links.findIndex((link) => link.classList.contains("active"));
        if (activeIdx !== -1) {
            expandForActive(activeIdx);
        }
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
    });
}
