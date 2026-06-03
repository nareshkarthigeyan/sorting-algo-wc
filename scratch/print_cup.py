# Combined header visualization
left_trophy = [
    "       .-----.     ",
    "     .'   __  '.   ",
    "    /   .'  '.  \\  ",
    "   |   |      |  | ",
    "    \\   '.__.'  /  ",
    "     '.       .'   ",
    "       )  _  (     ",
    "      /  ( )  \\    ",
    "     /  /   \\  \\   ",
    "    |  |  _  |  |  ",
    "    |  | ( ) |  |  ",
    "    |  |  V  |  |  ",
    "   /  /       \\  \\ ",
    "  |  |         |  |",
    "  |  |=========|  |",
    "  |  |=========|  |",
    " /  /===========\\  \\",
    "|_________________|",
    "|                 |"
]

# Right trophy is a direct mirror of left trophy
right_trophy = left_trophy

mid_block = [
    "                                      ", # L0
    "                                      ", # L1
    "                                      ", # L2
    "                                      ", # L3
    "                                      ", # L4
    "                                      ", # L5
    "                                      ", # L6
    "            .-=========-.             ", # L7
    "           /             \\            ", # L8
    "          |    SORTING    |           ", # L9
    "          |   WORLD CUP   |           ", # L10
    "          |     2026      |           ", # L11
    "           \\             /            ", # L12
    "            '-=========-'             ", # L13
    "                                      ", # L14
    "                                      ", # L15
    "                                      ", # L16
    "                                      ", # L17
    "                                      "  # L18
]

for i in range(19):
    left = left_trophy[i]
    mid = mid_block[i]
    right = right_trophy[i]
    # We want to print them side by side
    print(left + mid + right)
