"""Places the map visual can mark, as (latitude, longitude). Add more here if a video needs them."""
import re

PLACES = {
    "Delhi": (28.61, 77.21), "Mumbai": (19.08, 72.88), "Chennai": (13.08, 80.27), "Kolkata": (22.57, 88.36),
    "Bengaluru": (12.97, 77.59), "Hyderabad": (17.39, 78.49), "Pune": (18.52, 73.86), "Ahmedabad": (23.02, 72.57),
    "Jaipur": (26.91, 75.79), "Lucknow": (26.85, 80.95), "Patna": (25.59, 85.14), "Bhopal": (23.26, 77.41),
    "Guwahati": (26.14, 91.74), "Srinagar": (34.08, 74.80), "Jammu": (32.73, 74.86), "Prayagraj": (25.44, 81.85),
    "Varanasi": (25.32, 82.97), "Imphal": (24.82, 93.94), "Kochi": (9.93, 76.27), "Noida": (28.54, 77.39),
    "Gurugram": (28.46, 77.03), "Indore": (22.72, 75.86), "Nagpur": (21.15, 79.09), "Surat": (21.17, 72.83),
    "Chandigarh": (30.73, 76.78), "Ranchi": (23.34, 85.31), "Raipur": (21.25, 81.63), "Shimla": (31.10, 77.17),
    "Dehradun": (30.32, 78.03), "Thiruvananthapuram": (8.52, 76.94), "Goa": (15.30, 74.12),
    "Kashmir": (34.00, 75.00), "Ladakh": (34.20, 77.60), "Punjab": (31.10, 75.40), "Haryana": (29.10, 76.10),
    "Rajasthan": (26.90, 73.80), "Gujarat": (22.70, 71.60), "Maharashtra": (19.60, 75.70),
    "Karnataka": (15.00, 75.70), "Kerala": (10.30, 76.30), "Tamil Nadu": (11.00, 78.50),
    "Andhra Pradesh": (15.80, 79.80), "Telangana": (17.90, 79.00), "Odisha": (20.50, 84.40),
    "Chhattisgarh": (21.30, 81.80), "Jharkhand": (23.60, 85.50), "Bihar": (25.70, 85.70),
    "West Bengal": (23.50, 87.70), "Uttar Pradesh": (26.90, 80.50), "Madhya Pradesh": (23.50, 78.20),
    "Uttarakhand": (30.10, 79.20), "Himachal Pradesh": (31.90, 77.20), "Assam": (26.30, 92.80),
    "Manipur": (24.70, 93.90), "Nagaland": (26.10, 94.50), "Meghalaya": (25.50, 91.30), "Mizoram": (23.30, 92.80),
    "Tripura": (23.80, 91.60), "Arunachal Pradesh": (28.00, 94.60), "Sikkim": (27.50, 88.50),
}
ALIASES = {"Bangalore": "Bengaluru", "Bombay": "Mumbai", "Madras": "Chennai", "Calcutta": "Kolkata",
           "Allahabad": "Prayagraj", "Gurgaon": "Gurugram", "New Delhi": "Delhi", "Jammu and Kashmir": "Kashmir",
           "Jammu & Kashmir": "Kashmir", "J&K": "Kashmir", "Banaras": "Varanasi", "Benares": "Varanasi"}


def canonical(name):
    """The name in PLACES for a place, or None if the map doesn't know it."""
    text = str(name).strip().lower()
    for known in list(ALIASES) + list(PLACES):
        if known.lower() == text:
            return ALIASES.get(known, known)
    return None


def places_in(text, limit=6):
    """Places named in a sentence, in the order they're said."""
    found = []
    names = sorted(list(PLACES) + list(ALIASES), key=len, reverse=True)
    pattern = r"(?<![A-Za-z])(" + "|".join(re.escape(n) for n in names) + r")(?![A-Za-z])"
    for m in re.finditer(pattern, str(text)):   # case-sensitive: "goa" or "surat" in a sentence stay words
        name = canonical(m.group(1))
        if name not in found:
            found.append(name)
    return found[:limit]
