from __future__ import annotations

import re
from typing import TypedDict


class SectionKnowledge(TypedDict):
    sequence_number: str | None
    process_stage: str | None
    process_description: str | None


_SECTION_NUMBER = re.compile(r"^\s*(\d{1,3})\b")


# Operator-training descriptions for the TRIUMPH bag-making process. These are
# keyed by station number so display-label capitalization and wording can change
# without disconnecting a section from its description.
_KNOWLEDGE: dict[str, tuple[str, str]] = {
    "020": (
        "Main material infeed",
        "Holds and unwinds the main roll of paper or laminated material, feeding a continuous web into the machine.",
    ),
    "055": (
        "Main material infeed",
        "Supports and routes the main web between the unwinder and dancer. This section belongs to the main-material path and is not the bottom-patch supply.",
    ),
    "080": (
        "Web tension control",
        "Uses a movable dancer roller to buffer material and keep web tension stable as roll diameter or machine speed changes.",
    ),
    "085": (
        "Web alignment",
        "Measures the lateral position of the incoming web and steers it back into alignment before downstream processing.",
    ),
    "086": (
        "Perforation registration",
        "Reads a printed registration mark and gives the controller a repeat-position reference so needle perforations are placed correctly on each future bag. The print-mark sensor locates the bag pattern; it does not make the holes.",
    ),
    "087": (
        "Needle perforation",
        "Uses the needle mechanism to punch the specified ventilation-hole pattern into the material at the position established by registration control.",
    ),
    "088": (
        "Material splice detection",
        "Detects a taped or overlapped roll splice so the affected material can be tracked, rejected, or handled according to the machine sequence.",
    ),
    "090": (
        "Tube forming",
        "Folds the flat web into the required tube profile and establishes the side-gusset geometry used by the finished bag.",
    ),
    "100": (
        "Longitudinal seam",
        "Bonds the overlapping lengthwise edges of the folded web, converting it into a continuous bag tube.",
    ),
    "101": (
        "Longitudinal seam",
        "Monitors the longitudinal-sealing process and its operating conditions so seam position and formation remain consistent.",
    ),
    "102": (
        "Tube tension control",
        "Measures tension in the formed tube to identify conditions that could cause stretching, wrinkles, tracking errors, or register drift.",
    ),
    "105": (
        "Tube-section structure",
        "Provides the structural machine frame that supports the tube-forming and related web-handling mechanisms.",
    ),
    "106": (
        "Machine safety",
        "Monitors the safety guard doors around the tube section and prevents unsafe machine operation when an interlock is open.",
    ),
    "110": (
        "Seam draw and cooling",
        "Pulls the newly formed tube forward while the chill roll cools and stabilizes the longitudinal seam after bonding.",
    ),
    "124": (
        "Gusset preparation",
        "Preheats the side-gusset regions so the paper or laminated material folds and bonds consistently during later bottom-forming operations.",
    ),
    "150": (
        "Tube alignment",
        "Re-centers the formed tube after folding and longitudinal sealing, which can cause the material to shift laterally.",
    ),
    "160": (
        "Print registration and draw",
        "Reads the repeated print mark and adjusts the web draw so the printed design, cut position, bag length, and bottom operations stay registered to one another.",
    ),
    "200": (
        "Bag format",
        "Positions the adjustable guides and forming components for the selected bag width, length, gusset depth, and bottom dimensions.",
    ),
    "211": (
        "Machine safety",
        "Monitors the main TRIUMPH guard doors and safety interlocks that protect access to moving machine components.",
    ),
    "212": (
        "Machine support systems",
        "Represents supporting equipment and peripherals such as compressed air, vacuum, adhesive, heating, cooling, and auxiliary devices.",
    ),
    "220": (
        "Tube draw",
        "Uses driven rollers to advance the continuous tube toward the knife at the commanded length and timing.",
    ),
    "230": (
        "Tube cutting",
        "Cross-cuts the continuous tube into individual bag blanks at the registered bag length.",
    ),
    "240": (
        "Blank transport",
        "Transfers each cut bag blank into the bottom-making section while preserving its orientation, spacing, and timing.",
    ),
    "250": (
        "Bottom preparation",
        "Creates controlled crease lines that allow the bottom panels to open and fold into the intended geometry.",
    ),
    "260": (
        "Bottom forming",
        "Opens and shapes the end of each tube section into the block-bottom panels and flaps.",
    ),
    "265": (
        "Bottom adhesive application",
        "Applies hot-melt adhesive to the specified bottom-forming areas so the folded bottom components can be bonded.",
    ),
    "270": (
        "Bottom closing",
        "Folds the formed bottom flaps into their closed position over the applied adhesive.",
    ),
    "280": (
        "Bottom-section transport",
        "Provides the main controlled draw through the bottom-making area and maintains the timing and spacing of individual bags.",
    ),
    "290": (
        "Bag positioning",
        "Carries and positions the formed bags on a controlled cylinder path, maintaining pitch and presenting each bottom for the bottom-patch operation.",
    ),
    "300": (
        "Bottom-patch supply",
        "Holds and unwinds the separate bottom-patch roll used to reinforce and finish the bag bottom.",
    ),
    "320": (
        "Bottom-patch web routing",
        "Redirects the bottom-patch web into the direction and orientation required by the patch preparation section.",
    ),
    "330": (
        "Bottom-patch alignment",
        "Measures and corrects the lateral position of the bottom-patch web before it is prepared and applied.",
    ),
    "340": (
        "Bottom-patch preparation",
        "Feeds, measures, and prepares the bottom-patch material for transfer, including separation into the required patch length.",
    ),
    "350": (
        "Bottom-patch transfer",
        "Synchronizes each prepared bottom patch with a bag and transfers it onto the formed bag bottom.",
    ),
    "360": (
        "Bottom-patch sealing",
        "Bonds the bottom patch to the closed bag bottom using the configured combination of heat, pressure, and adhesive.",
    ),
    "980": (
        "Bond conditioning",
        "Provides controlled temperature and dwell time so the newly formed bottom and bottom-patch bonds stabilize consistently.",
    ),
    "990": (
        "Final cooling",
        "Cools and sets the bonded areas before finished bags leave the process, reducing distortion and preventing hot adhesive from shifting.",
    ),
}

_SCRAP_KNOWLEDGE = (
    "Waste and rejection",
    "Collects rejected bags, splice-affected material, trims, and other unusable process material.",
)


def get_section_knowledge(section_key: str | None) -> SectionKnowledge:
    """Return training metadata for a machine section without requiring DB changes."""
    raw_key = str(section_key or "").strip()
    match = _SECTION_NUMBER.match(raw_key)
    sequence_number = match.group(1).zfill(3) if match else None
    entry = _KNOWLEDGE.get(sequence_number or "")
    if entry is None and raw_key.lower() == "scrap":
        entry = _SCRAP_KNOWLEDGE
    if entry is None:
        return {
            "sequence_number": sequence_number,
            "process_stage": None,
            "process_description": None,
        }
    stage, description = entry
    return {
        "sequence_number": sequence_number,
        "process_stage": stage,
        "process_description": description,
    }

