from research_engine.domain.models import NicheRecord


class NicheUniverseEngine:
    def get_stub_universe(self) -> list[NicheRecord]:
        return [
            NicheRecord("niche-001", "kitchen", "thermos", "Thermos 1L", 1200, 11_500_000, 9600, 0.58, 8.2, "low"),
            NicheRecord("niche-002", "kitchen", "organizers", "Spice Organizer", 890, 6_200_000, 7100, 0.42, 7.5, "low"),
            NicheRecord("niche-003", "backpacks", "city_backpacks", "Urban Backpack", 2400, 12_800_000, 5300, 0.73, 5.1, "medium"),
            NicheRecord("niche-004", "bathroom", "dispensers", "Soap Dispenser", 760, 5_900_000, 7800, 0.39, 6.7, "low"),
            NicheRecord("niche-005", "kitchen", "containers", "Storage Containers", 980, 8_700_000, 8200, 0.47, 9.3, "low"),
            NicheRecord("niche-006", "auto", "holders", "Phone Holder", 1300, 10_200_000, 7600, 0.66, 4.4, "medium"),
            NicheRecord("niche-007", "pets", "bowls", "Anti-Slip Bowl", 740, 4_300_000, 6200, 0.31, 6.1, "low"),
            NicheRecord("niche-008", "garden", "tools", "Garden Tool Set", 2100, 7_600_000, 3400, 0.45, 10.5, "high"),
            NicheRecord("niche-009", "home", "cleaning", "Cleaning Brush", 680, 4_700_000, 6900, 0.52, 4.9, "low"),
            NicheRecord("niche-010", "kitchen", "bottles", "Oil Bottle", 820, 3_900_000, 4900, 0.29, 6.0, "low"),
            NicheRecord("niche-011", "storage", "boxes", "Storage Box", 1450, 9_100_000, 5100, 0.41, 7.8, "low"),
            NicheRecord("niche-012", "bathroom", "shelves", "Corner Shelf", 1690, 6_800_000, 3700, 0.54, 8.8, "low"),
            NicheRecord("niche-013", "pets", "toys", "Dog Toy", 550, 2_900_000, 5200, 0.36, 5.4, "low"),
            NicheRecord("niche-014", "auto", "organizers", "Trunk Organizer", 1990, 8_300_000, 4200, 0.62, 7.1, "medium"),
            NicheRecord("niche-015", "kitchen", "cutting_boards", "Cutting Board Set", 1590, 7_200_000, 4500, 0.48, 5.9, "low"),
            NicheRecord("niche-016", "home", "lighting", "Sensor Night Light", 990, 5_500_000, 5600, 0.67, 11.2, "medium"),
            NicheRecord("niche-017", "garden", "watering", "Water Sprayer", 870, 3_700_000, 4300, 0.28, 12.7, "high"),
            NicheRecord("niche-018", "kids", "feeding", "Silicone Feeding Kit", 2200, 10_900_000, 4700, 0.71, 9.9, "medium"),
            NicheRecord("niche-019", "beauty", "styling", "Styling Brush", 1350, 6_100_000, 4000, 0.64, 8.0, "low"),
            NicheRecord("niche-020", "storage", "drawer_dividers", "Drawer Dividers", 930, 4_200_000, 5400, 0.34, 6.4, "low"),
            NicheRecord("niche-021", "kitchen", "lunch_boxes", "Leakproof Lunch Box", 1100, 7_900_000, 6900, 0.57, 7.3, "medium"),
            NicheRecord("niche-022", "bathroom", "mats", "Anti-Slip Bath Mat", 1250, 5_200_000, 3900, 0.43, 4.6, "low"),
            NicheRecord("niche-023", "pets", "carriers", "Foldable Pet Carrier", 2600, 6_600_000, 2500, 0.52, 6.9, "medium"),
            NicheRecord("niche-024", "auto", "seat_covers", "Seat Cover", 1750, 7_300_000, 4100, 0.69, 5.5, "medium"),
        ]
