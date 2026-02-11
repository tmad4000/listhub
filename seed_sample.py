#!/usr/bin/env python3
"""Seed sample data with folder structure for demo users."""
import sqlite3
import os
from nanoid import generate as nanoid

DB_PATH = os.environ.get('LISTHUB_DB', 'listhub.db')

ALICE_ITEMS = [
    # Root items
    {"slug": "welcome", "title": "Welcome to My ListHub", "file_path": "welcome.md",
     "item_type": "note", "visibility": "public", "tags": ["intro"],
     "content": "# Welcome\n\nThis is my public ListHub. I share reading lists, recipes, travel notes, and project ideas here.\n\nFeel free to explore!"},

    # recipes/ folder
    {"slug": "pasta-aglio-olio", "title": "Pasta Aglio e Olio", "file_path": "recipes/pasta-aglio-olio.md",
     "item_type": "note", "visibility": "public", "tags": ["recipes", "italian"],
     "content": "# Pasta Aglio e Olio\n\n## Ingredients\n- 400g spaghetti\n- 6 cloves garlic, thinly sliced\n- 1/2 cup olive oil\n- 1 tsp red pepper flakes\n- Fresh parsley\n- Parmesan\n\n## Steps\n1. Cook spaghetti al dente\n2. Sautee garlic in olive oil until golden\n3. Add pepper flakes\n4. Toss with pasta and pasta water\n5. Finish with parsley and parmesan"},

    {"slug": "banana-bread", "title": "Banana Bread", "file_path": "recipes/banana-bread.md",
     "item_type": "note", "visibility": "public", "tags": ["recipes", "baking"],
     "content": "# Banana Bread\n\n## Ingredients\n- 3 ripe bananas\n- 1/3 cup melted butter\n- 3/4 cup sugar\n- 1 egg\n- 1 tsp vanilla\n- 1 tsp baking soda\n- 1.5 cups flour\n\n## Steps\n1. Mash bananas, mix with butter\n2. Add sugar, egg, vanilla\n3. Fold in baking soda and flour\n4. Bake at 350F for 60 min"},

    {"slug": "thai-green-curry", "title": "Thai Green Curry", "file_path": "recipes/thai-green-curry.md",
     "item_type": "note", "visibility": "public", "tags": ["recipes", "thai"],
     "content": "# Thai Green Curry\n\n## Ingredients\n- Green curry paste\n- Coconut milk\n- Chicken or tofu\n- Thai basil\n- Bamboo shoots\n- Fish sauce\n- Palm sugar\n\n## Steps\n1. Fry curry paste in coconut cream until fragrant\n2. Add protein, cook through\n3. Add coconut milk, bamboo shoots\n4. Season with fish sauce and sugar\n5. Finish with Thai basil"},

    # travel/ folder
    {"slug": "tokyo-2025", "title": "Tokyo Trip Notes", "file_path": "travel/tokyo-2025.md",
     "item_type": "note", "visibility": "public", "tags": ["travel", "japan"],
     "content": "# Tokyo 2025\n\n## Day 1 - Shibuya & Shinjuku\n- Shibuya crossing at sunset\n- Meiji Shrine morning walk\n- Golden Gai for evening drinks\n\n## Day 2 - Asakusa & Akihabara\n- Senso-ji temple\n- Nakamise shopping street\n- Electric Town for vintage electronics\n\n## Day 3 - Tsukiji & Ginza\n- Outer market breakfast (fresh sushi)\n- TeamLab Borderless\n- Ginza department stores"},

    {"slug": "portugal-recs", "title": "Portugal Recommendations", "file_path": "travel/portugal-recs.md",
     "item_type": "list", "visibility": "public", "tags": ["travel", "portugal"],
     "content": "# Portugal\n\n## Lisbon\n- Time Out Market for food\n- Tram 28 through Alfama\n- Pasteis de Belem\n- LX Factory\n\n## Porto\n- Livraria Lello bookshop\n- Port wine cellars in Vila Nova de Gaia\n- Ribeira district\n\n## Algarve\n- Benagil cave (kayak at dawn)\n- Praia da Marinha\n- Lagos old town"},

    {"slug": "packing-checklist", "title": "Packing Checklist", "file_path": "travel/packing-checklist.md",
     "item_type": "list", "visibility": "public", "tags": ["travel"],
     "content": "# Packing Checklist\n\n## Always\n- [ ] Passport\n- [ ] Phone charger + adapter\n- [ ] Headphones\n- [ ] Toiletries bag\n- [ ] Medications\n\n## Warm Climate\n- [ ] Sunscreen\n- [ ] Sunglasses\n- [ ] Light layers\n\n## Cold Climate\n- [ ] Down jacket\n- [ ] Thermals\n- [ ] Gloves + beanie"},

    # reading/ folder
    {"slug": "2025-reading", "title": "2025 Reading List", "file_path": "reading/2025-reading.md",
     "item_type": "list", "visibility": "public", "tags": ["books", "reading"],
     "content": "# 2025 Reading List\n\n## Read\n- **The Ministry for the Future** by Kim Stanley Robinson ★★★★★\n- **Klara and the Sun** by Kazuo Ishiguro ★★★★\n- **Piranesi** by Susanna Clarke ★★★★★\n\n## Currently Reading\n- **The Dispossessed** by Ursula K. Le Guin\n\n## Want to Read\n- Oryx and Crake by Margaret Atwood\n- Children of Time by Adrian Tchaikovsky\n- Project Hail Mary by Andy Weir"},

    {"slug": "sci-fi-favorites", "title": "Favorite Sci-Fi", "file_path": "reading/sci-fi-favorites.md",
     "item_type": "list", "visibility": "public", "tags": ["books", "sci-fi"],
     "content": "# Favorite Sci-Fi Books\n\n1. **Dune** — Frank Herbert\n2. **Neuromancer** — William Gibson\n3. **Left Hand of Darkness** — Ursula K. Le Guin\n4. **Snow Crash** — Neal Stephenson\n5. **Blindsight** — Peter Watts\n6. **The Three-Body Problem** — Liu Cixin\n7. **Hyperion** — Dan Simmons\n8. **A Fire Upon the Deep** — Vernor Vinge"},

    # projects/ folder
    {"slug": "garden-tracker", "title": "Garden Tracker App", "file_path": "projects/garden-tracker.md",
     "item_type": "note", "visibility": "public", "tags": ["projects", "ideas"],
     "content": "# Garden Tracker\n\nApp idea: track what you plant, when, and how it grows.\n\n## Features\n- Photo timeline per plant\n- Watering reminders\n- Harvest log\n- Companion planting suggestions\n- Frost date alerts by location\n\n## Stack\n- React Native for mobile\n- Supabase backend\n- Plant API for species data"},

    {"slug": "reading-log-api", "title": "Reading Log API", "file_path": "projects/reading-log-api.md",
     "item_type": "note", "visibility": "public", "tags": ["projects", "api"],
     "content": "# Reading Log API\n\nA simple REST API to track books read.\n\n## Endpoints\n```\nPOST /books      - Add a book\nGET  /books      - List all books\nPUT  /books/:id  - Update (rating, notes)\nGET  /stats      - Reading stats (per month/year)\n```\n\n## Data Model\n- title, author, isbn\n- started_at, finished_at\n- rating (1-5)\n- notes (markdown)\n- tags"},

    # projects/garden/ subfolder (3 levels deep)
    {"slug": "garden-soil-notes", "title": "Soil Research", "file_path": "projects/garden/soil-notes.md",
     "item_type": "note", "visibility": "public", "tags": ["projects", "garden"],
     "content": "# Soil Research\n\n## pH Levels\n- Most vegetables: 6.0-7.0\n- Blueberries: 4.5-5.5\n- Lavender: 6.5-7.5\n\n## Amendments\n- **Compost**: improves structure and nutrients\n- **Perlite**: improves drainage\n- **Peat moss**: retains moisture (acidic)\n- **Lime**: raises pH\n- **Sulfur**: lowers pH"},
]


def seed():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    # Get alice's user ID
    alice = db.execute("SELECT id FROM user WHERE username = 'alice'").fetchone()
    if not alice:
        print("User 'alice' not found. Skipping.")
        return

    alice_id = alice['id']

    # Delete alice's existing items
    existing = db.execute("SELECT id, rowid FROM item WHERE owner_id = ?", (alice_id,)).fetchall()
    for item in existing:
        db.execute("DELETE FROM item_fts WHERE rowid = ?", (item['rowid'],))
        db.execute("DELETE FROM item_tag WHERE item_id = ?", (item['id'],))
        db.execute("DELETE FROM item_version WHERE item_id = ?", (item['id'],))
    db.execute("DELETE FROM item WHERE owner_id = ?", (alice_id,))
    db.commit()
    print(f"Cleared {len(existing)} existing items for alice")

    # Insert new items
    for data in ALICE_ITEMS:
        item_id = nanoid()
        db.execute(
            "INSERT INTO item (id, owner_id, slug, title, content, file_path, item_type, visibility) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, alice_id, data['slug'], data['title'], data['content'],
             data['file_path'], data['item_type'], data['visibility'])
        )

        # Tags
        for tag in data.get('tags', []):
            db.execute("INSERT OR IGNORE INTO item_tag (item_id, tag) VALUES (?, ?)", (item_id, tag))

        # Version
        db.execute(
            "INSERT INTO item_version (item_id, content, revision) VALUES (?, ?, 1)",
            (item_id, data['content'])
        )

        # FTS
        tags_str = ' '.join(data.get('tags', []))
        row = db.execute("SELECT rowid FROM item WHERE id = ?", (item_id,)).fetchone()
        db.execute(
            "INSERT INTO item_fts (rowid, title, content, tags) VALUES (?, ?, ?, ?)",
            (row['rowid'], data['title'], data['content'], tags_str)
        )

        print(f"  + {data['file_path']}")

    db.commit()
    print(f"\nSeeded {len(ALICE_ITEMS)} items for alice")


if __name__ == '__main__':
    seed()
