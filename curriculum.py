"""Long-term sequence kept LOCALLY (the app only ever holds the next 7 days).
Edit these queues to steer; nightly.py consumes them in order."""

# Letter spine in synthetic-phonics order. Each letter yields, over ~a week:
#   day 0: "Letter X" (the extra-practice lesson the child actually does)  ->  ~+5d: "Uppercase X" (review)  ->  ~+7d: "Beginning Sound x"
LETTERS = list("stinpcehrdgoulfbjwkvxyzq")

# Skill track (one per day, alternating math / phonological), in prerequisite order. (title, level)
SKILLS = [
    ("Count 4 Objects", "Main"), ("Beginning Sounds 1", "Main"), ("Tap & Count to 5", "Main"),
    ("Blend Sounds 2", "Main"), ("Grouping: More", "Main"), ("Word Families", "Main"),
    ("Circle", "Main"), ("Beginning Sounds 2", "Main"), ("Square", "Main"), ("Words: End Sound", "Main"),
    ("Add Within 3", "Main"), ("Triangle", "Main"), ("Subtract Within 3", "Main"), ("Rectangle", "Main"),
    ("Patterns", "Main"), ("Number Combos", "Main"), ("Last in Line", "Main"), ("Measurement", "Main"),
    ("Positions", "Main"), ("Other Colors", "Main"),
]

# Third slot: books / print / sorting, easy and motivating, in order.
BOOKS = [
    "Mud", "Baby Dogs", "Sad Ollo", "Baby Horses", "Fruit", "Weather", "Baby Gorillas", "Kangaroos", "The Big Bed",
    "Baby Hippos", "What Is It?", "Baby Pandas", "Jam in the Vat", "Baby Elephants", "So Hot", "Snakes", "Kitchen",
    "Butterflies", "Hop Hop Hop", "Baby Rabbits", "Around the House", "Baby Pigs", "The Cup Is Up", "Baby Cats",
    "Leaf Cutter Ants", "Look At My Pen", "Seeds Grow", "Opposites 1", "Food for Fido", "Opposites 2",
    # added 10/4 for the 10-a-day load (titles from the 9/7 All Progress capture)
    "Baby Ducks", "Look at It Go", "Baby Tigers", "Come On", "Peck's Big Day", "Gum on the Rug", "Fun to Read", "The Big Fish",
    "Looking at Eggs", "The Box", "Baby on Board", "Race to the Lake", "Out at Night", "A Nice Day", "Animal Groups", "Ollo's Bike",
    "Walk with Camels", "Peck Plays a Tune", "Bird Beaks", "Why", "Beaver Builders", "Being Together", "Cool Beans", "Drip Drop",
    "On the Move", "Plates on My Plate",
]

# Enrichment (parent 10/4, 10 lessons a day): real work that is NOT new material. Practice levels of skills the child had mastered before
# September, vocabulary, and pre-writing. Used to top a day up to 10 after the letter, reviews, one new skill and two books,
# so the load never forces new skills faster than one a day. Easy -> hard, interleaved by domain.
ENRICH = [
    ("Farm Animals", "Practice 1"), ("Count 1 & 2", "Practice 2"), ("Words on Signs 2", "Main"), ("Vehicles", "Practice 1"),
    ("Secondary Colors", "Practice 1"), ("Blend Sounds 1", "Practice 1"), ("Animals & Colors", "Practice 1"),
    ("Number Hunt 1-3", "Practice 1"), ("Words on Signs 1", "Practice 1"), ("Jungle Animals", "Practice 1"),
    ("Compare Sizes", "Practice 1"), ("Lines and Circles", "Main"), ("Primary Colors", "Practice 2"),
    ("Title & Author", "Practice 1"), ("Draw Lines", "Main"), ("Compare Sizes", "Practice 2"), ("Letters, Numbers", "Main"),
    ("Blend Sounds 1", "Practice 2"), ("Farm Animals", "Practice 2"), ("Write Words", "Main"), ("Vehicles", "Practice 2"),
    ("Draw Lines, Shapes", "Main"), ("Animals & Colors", "Practice 2"), ("Jungle Animals", "Practice 2"),
]

# Spaced-review policy: after a MAIN score >= 90, schedule Practice 1 at +7d and Practice 2 at +17d;
# 70-89: Practice 1 at +5d; < 70: Basic at +2d, then Main again at +9d.
def review_schedule(score, level="Main"):
    """What to schedule after a scored attempt at `level`. (level, +days)"""
    if score is None: return []
    if level == "Main":
        if score >= 90: return [("Practice 1", 7), ("Practice 2", 17)]
        if score >= 70: return [("Practice 1", 5)]
        return [("Basic", 2), ("Main", 9)]
    if level == "Practice 1":
        if score >= 90: return [("Practice 2", 10)]
        if score >= 70: return [("Practice 1", 7)]
        return [("Basic", 2), ("Main", 9)]
    if level == "Practice 2":
        return [] if score >= 90 else [("Practice 1", 7)]
    if level == "Basic":
        return [("Main", 5)] if score >= 70 else [("Basic", 4)]
    return []

# Items that are NOT on the critical path: if the child skips one, drop it rather than carry it forward.
OPTIONAL = set(BOOKS)

# Horizon (parent, 9/11 evening): the app only holds the current day and the next day; nightly fills tomorrow + 1 buffer day.
HORIZON_DAYS = 7        # parent 10/4: keep a full week assigned so a missed pass never leaves them in free play

# Weekend load
WEEKDAY_SLOTS, WEEKEND_SLOTS = 10, 10   # parent 10/4: 10 good lessons every day so the child never runs out and drifts into free play; unfinished ones roll forward
