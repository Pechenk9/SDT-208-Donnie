
INGREDIENT_GROUPS = [
    {
        "name": "Dough",
        "max_selections": 1,
    },
    {
        "name": "Filling",
        "max_selections": 1,
    },
    {
        "name": "Glaze",
        "max_selections": 1,
    },
    {
        "name": "Toppings",
        "max_selections": 3,
    },
]

INGREDIENTS = [
    {
        "name": "Classic dough",
        "description": "Traditional soft and fluffy donut dough.",
        "group": "Dough",
        "extra_price": "0.00",
    },
    {
        "name": "Chocolate dough",
        "description": "Soft dough with cocoa flavor.",
        "group": "Dough",
        "extra_price": "0.30",
    },
    {
        "name": "Strawberry cream",
        "description": "Sweet cream with strawberry flavor.",
        "group": "Filling",
        "extra_price": "0.40",
    },
    {
        "name": "Banana cream",
        "description": "Smooth cream with natural banana flavor.",
        "group": "Filling",
        "extra_price": "0.40",
    },
    {
        "name": "Chocolate cream",
        "description": "Rich chocolate filling.",
        "group": "Filling",
        "extra_price": "0.50",
    },
    {
        "name": "Pistachio cream",
        "description": "Creamy pistachio filling.",
        "group": "Filling",
        "extra_price": "0.80",
    },
    {
        "name": "Blueberry jam",
        "description": "Sweet blueberry fruit filling.",
        "group": "Filling",
        "extra_price": "0.50",
    },
    {
        "name": "Vanilla cream",
        "description": "Classic smooth vanilla filling.",
        "group": "Filling",
        "extra_price": "0.40",
    },
    {
        "name": "Coffee cream",
        "description": "Cream filling with cappuccino flavor.",
        "group": "Filling",
        "extra_price": "0.50",
    },
    {
        "name": "Strawberry glaze",
        "description": "Sweet strawberry-flavored coating.",
        "group": "Glaze",
        "extra_price": "0.30",
    },
    {
        "name": "Dark chocolate glaze",
        "description": "Rich dark chocolate coating.",
        "group": "Glaze",
        "extra_price": "0.40",
    },
    {
        "name": "White chocolate glaze",
        "description": "Smooth white chocolate coating.",
        "group": "Glaze",
        "extra_price": "0.40",
    },
    {
        "name": "Pistachio glaze",
        "description": "Pistachio-flavored sweet coating.",
        "group": "Glaze",
        "extra_price": "0.60",
    },
    {
        "name": "Blueberry glaze",
        "description": "Blueberry-flavored sweet coating.",
        "group": "Glaze",
        "extra_price": "0.40",
    },
    {
        "name": "Chocolate stripes",
        "description": "Decorative chocolate stripes.",
        "group": "Toppings",
        "extra_price": "0.10",
    },
    {
        "name": "Crushed pistachios",
        "description": "Finely chopped pistachio nuts.",
        "group": "Toppings",
        "extra_price": "0.40",
    },
    {
        "name": "Chocolate sprinkles",
        "description": "Small chocolate decorations.",
        "group": "Toppings",
        "extra_price": "0.15",
    },
    {
        "name": "Pink sprinkles",
        "description": "Colorful pink sugar decorations.",
        "group": "Toppings",
        "extra_price": "0.15",
    },
    {
        "name": "Cookie crumbs",
        "description": "Crunchy crushed cookie topping.",
        "group": "Toppings",
        "extra_price": "0.20",
    },
]

PRODUCTS = [
    {
        "name": "Strawberry",
        "base_price": "3.50",
        "description": "A classic donut with delicate strawberry glaze and a sweet summer aroma.",
        "image_url": "https://donut.com.ua/components/com_jshopping/files/img_products/thumb_STRAWBERRY.png",
        "calories": 320,
    },
    {
        "name": "Bananada",
        "base_price": "3.60",
        "description": "A bright combination of banana flavor and chocolate stripes.",
        "image_url": "https://donut.com.ua/components/com_jshopping/files/img_products/thumb_444.png",
        "calories": 330,
    },
    {
        "name": "Chocopo",
        "base_price": "3.60",
        "description": "A rich chocolate donut covered with dark chocolate ganache.",
        "image_url": "https://donut.com.ua/components/com_jshopping/files/img_products/thumb_555.png",
        "calories": 350,
    },
    {
        "name": "Pistachio",
        "base_price": "4.00",
        "description": "An elegant donut with pistachio cream and delicate green glaze.",
        "image_url": "https://donut.com.ua/components/com_jshopping/files/img_products/thumb_333.png",
        "calories": 360,
    },
    {
        "name": "Blue Berry",
        "base_price": "3.75",
        "description": "A forest blueberry flavor with perfectly balanced sweetness.",
        "image_url": "https://donut.com.ua/components/com_jshopping/files/img_products/thumb_BLUE_BERRY.png",
        "calories": 325,
    },
    {
        "name": "Whittie",
        "base_price": "3.60",
        "description": "A delicate donut with vanilla flavor and pink decoration.",
        "image_url": "https://donut.com.ua/components/com_jshopping/files/img_products/thumb_22.png",
        "calories": 315,
    },
    {
        "name": "Choco",
        "base_price": "4.20",
        "description": "An intense chocolate experience for chocolate lovers.",
        "image_url": "https://donut.com.ua/components/com_jshopping/files/img_products/thumb_CHOCO_BOOM__1_.png",
        "calories": 380,
    },
    {
        "name": "Cappuccino",
        "base_price": "3.80",
        "description": "An aromatic coffee donut with a smooth creamy aftertaste.",
        "image_url": "https://donut.com.ua/components/com_jshopping/files/img_products/thumb_Cappuccino.png",
        "calories": 340,
    },
    {
    "name": "Blueberry Boom",
    "base_price": "4.50",
    "description": "An extra blueberry experience with a double layer of glaze.",
    "image_url": "https://donut.com.ua/components/com_jshopping/files/img_products/thumb_thumb_BLUEBARRY_BOOM_3.png",
    "calories": 390,
},
]

RECIPES = {
    "Strawberry": [
        ("Classic dough", "70.000", "100.000", "g", True),
        ("Strawberry cream", "18.000", "40.000", "g", True),
        ("Strawberry glaze", "20.000", "40.000", "g", True),
        ("Pink sprinkles", "3.000", "10.000", "g", True),
    ],
    "Bananada": [
        ("Classic dough", "70.000", "100.000", "g", True),
        ("Banana cream", "18.000", "40.000", "g", True),
        ("Dark chocolate glaze", "20.000", "40.000", "g", True),
        ("Chocolate stripes", "3.000", "10.000", "g", True),
    ],
    "Chocopo": [
        ("Chocolate dough", "70.000", "100.000", "g", True),
        ("Chocolate cream", "20.000", "40.000", "g", True),
        ("Dark chocolate glaze", "25.000", "40.000", "g", True),
    ],
    "Pistachio": [
        ("Classic dough", "70.000", "100.000", "g", True),
        ("Pistachio cream", "20.000", "40.000", "g", True),
        ("Pistachio glaze", "20.000", "40.000", "g", True),
        ("Crushed pistachios", "4.000", "10.000", "g", True),
    ],
    "Blue Berry": [
        ("Classic dough", "70.000", "100.000", "g", True),
        ("Blueberry jam", "18.000", "40.000", "g", True),
        ("Blueberry glaze", "20.000", "40.000", "g", True),
    ],
    "Whittie": [
        ("Classic dough", "70.000", "100.000", "g", True),
        ("Vanilla cream", "18.000", "40.000", "g", True),
        ("White chocolate glaze", "20.000", "40.000", "g", True),
        ("Pink sprinkles", "3.000", "10.000", "g", True),
    ],
    "Choco": [
        ("Chocolate dough", "70.000", "100.000", "g", True),
        ("Chocolate cream", "25.000", "40.000", "g", True),
        ("Dark chocolate glaze", "25.000", "40.000", "g", True),
        ("Chocolate sprinkles", "3.000", "10.000", "g", True),
    ],
    "Cappuccino": [
        ("Classic dough", "70.000", "100.000", "g", True),
        ("Coffee cream", "18.000", "40.000", "g", True),
        ("White chocolate glaze", "20.000", "40.000", "g", True),
        ("Chocolate stripes", "3.000", "10.000", "g", True),
    ],
    "Blueberry Boom": [
        ("Classic dough", "70.000", "100.000", "g", True),
        ("Blueberry jam", "25.000", "40.000", "g", True),
        ("Blueberry glaze", "30.000", "40.000", "g", True),
        ("Cookie crumbs", "4.000", "10.000", "g", True),
    ],
}

BRANCHES = [
    {
        "code": "LVIV-01",
        "name": "Donnie Lviv",
        "city": "Lviv",
        "address": "1 Rynok Square",
    },
    {
        "code": "KYIV-01",
        "name": "Donnie Kyiv",
        "city": "Kyiv",
        "address": "1 Khreshchatyk Street",
    },
    {
        "code": "ODESA-01",
        "name": "Donnie Odesa",
        "city": "Odesa",
        "address": "1 Deribasivska Street",
    },
]