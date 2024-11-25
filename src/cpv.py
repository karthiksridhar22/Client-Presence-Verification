import math

def calculate_owds_mp(eij):
    """
    Calculates the OWD estimates using the Minimum Pairs protocol.

    :param eij: Dictionary containing eij values (dic + dcj) for i,j in {1,2,3}
    :return: Dictionary of xi estimates (OWDs from verifiers to client)
    """
    # Step 1: For each pair (i, j), select the minimum of eij and eji
    m = {}
    pairs = [(1, 2), (2, 3), (3, 1)]
    for i, j in pairs:
        e_ij = eij.get((i, j), float('inf'))
        e_ji = eij.get((j, i), float('inf'))
        m[(i, j)] = min(e_ij, e_ji)

    # Step 2: Solve for xi using the equations xi + xj = m_ij
    # xi represents the smaller of dic and dci for each verifier
    # We have three equations:
    # x1 + x2 = m12
    # x2 + x3 = m23
    # x3 + x1 = m31

    # Extract m values
    m12 = m.get((1, 2), 0)
    m23 = m.get((2, 3), 0)
    m31 = m.get((3, 1), 0)

    # Solve the equations
    x1 = (m12 + m31 - m23) / 2
    x2 = m12 - x1
    x3 = m31 - x1

    xi = {1: x1, 2: x2, 3: x3}

    return xi


def calculate_verifier_owds(dv):
    """
    Selects the minimum OWDs between verifiers.

    :param dv: Dictionary containing OWDs between verifiers
    :return: Dictionary of yi estimates (OWDs between verifiers)
    """
    yi = {}
    pairs = [(1, 2), (2, 3), (3, 1)]
    for i, j in pairs:
        yi[i] = dv.get((i, j), float('inf'))
    return yi


def area_of_triangle(a, b, c):
    """
    Calculates the area of a triangle given its side lengths using Heron's formula.

    :param a: Length of side a
    :param b: Length of side b
    :param c: Length of side c
    :return: Area of the triangle
    """
    s = (a + b + c) / 2  # Semi-perimeter
    area_squared = s * (s - a) * (s - b) * (s - c)
    if area_squared <= 0:
        return 0
    return math.sqrt(area_squared)


def is_client_within_triangle(xi, yi):
    """
    Determines if the client is within the triangle formed by the verifiers.

    :param xi: Dictionary of estimated OWDs from client to verifiers (xi)
    :param yi: Dictionary of OWDs between verifiers (yi)
    :return: True if client is within the triangle, False otherwise
    """
    # Map delays to distances (assuming 1 ms = 200 km for simplicity)
    # This is to account for the minimal delays on a LAN
    # Convert delays from seconds to milliseconds
    xi_ms = {k: v * 1000 for k, v in xi.items()}
    yi_ms = {k: v * 1000 for k, v in yi.items()}

    # Apply a scaling factor to represent distances
    scaling_factor = 200  # km per ms
    xi_scaled = {k: v * scaling_factor for k, v in xi_ms.items()}
    yi_scaled = {k: v * scaling_factor for k, v in yi_ms.items()}

    # Calculate areas
    # area_v: Area of the triangle formed by the verifiers
    # area_c: Sum of areas of triangles formed by the client and verifiers
    sides_v = [
        yi_scaled.get(1, 0),  # Between verifier 1 and 2
        yi_scaled.get(2, 0),  # Between verifier 2 and 3
        yi_scaled.get(3, 0),  # Between verifier 3 and 1
    ]
    area_v = area_of_triangle(*sides_v)

    sides_c = []
    # Triangles formed by client and pairs of verifiers
    for i in range(1, 4):
        a = xi_scaled.get(i, 0)
        b = xi_scaled.get((i % 3) + 1, 0)
        c = yi_scaled.get(i, 0)
        area = area_of_triangle(a, b, c)
        sides_c.append(area)

    area_c = sum(sides_c)

    # Check if the client is within the triangle
    # If the sum of areas equals the area of the verifier triangle, the client is inside
    # Allow for a larger tolerance due to minimal delays on LAN
    tolerance = 0.2 * area_v  # 20% tolerance
    if abs(area_c - area_v) <= tolerance:
        return True
    else:
        return False
