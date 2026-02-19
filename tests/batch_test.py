"""Batch test: run real Discord message addresses through the parser."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from bot.utils.address_parser import parse_address

# Each tuple: (input_text, expected_dict_subset)
# We only check fields that matter; empty string means we expect empty.
CASES = [
    # 1. Standard multi-line
    ("Benji Stratton\n14706 n 92 ave\nPeoria Az 85381\n\nGreen cardholder",
     {"name": "Benji Stratton", "street": "14706 N 92 Ave", "city": "Peoria", "state": "AZ", "zip": "85381"}),

    # 2. ZIP on its own line, full state name on previous line
    ("Gavin Friel\n82 Broken Bow Lane\nEast Falmouth, Massachusetts \n02536\n\nBrown Hat",
     {"name": "Gavin Friel", "street": "82 Broken Bow Lane", "city": "East Falmouth", "state": "MA", "zip": "02536"}),

    # 3. Inline street+city/state/zip no comma between street and city
    ("Jae Simbol\n5037 n valley center Ave Covina ca 91724\n\nNew black Goyard card wallet",
     {"name": "Jae Simbol", "street": "5037 N Valley Center Ave", "city": "Covina", "state": "CA", "zip": "91724"}),

    # 4. Inline with comma, grid-ish address
    ("Kevin Russell\n2109 N 150 W Anderson, IN 46011\n\nWhite card wallet",
     {"name": "Kevin Russell", "city": "Anderson", "state": "IN", "zip": "46011"}),

    # 5. Apt on same line as street (Apt. #)
    ("John Degala\n\n3815 Eastside Street Apt. #8014\nHouston, TX 77098\n\nBlack card wallet",
     {"name": "John Degala", "city": "Houston", "state": "TX", "zip": "77098"}),

    # 6. Standard inline
    ("Alexander Mahoney\n2157 Sterling drive\nRocklin CA 95765\n\nNew Black Wallet",
     {"name": "Alexander Mahoney", "street": "2157 Sterling Drive", "city": "Rocklin", "state": "CA", "zip": "95765"}),

    # 7. City/state on one line, zip on next
    ("isaac gonzalez \n1627 Ronan ave \nwilmington CA \n90744\n\nAcne Jeans 48",
     {"name": "Isaac Gonzalez", "street": "1627 Ronan Ave", "city": "Wilmington", "state": "CA", "zip": "90744"}),

    # 8. Full state name, city/state/zip on one line
    ("wilmer acosta\n5837 Greenway vista ln\ncharlotte north carolina 28216\n\ngreen streete Xl",
     {"name": "Wilmer Acosta", "street": "5837 Greenway Vista Ln", "city": "Charlotte", "state": "NC", "zip": "28216"}),

    # 9. "new" noise line before address
    ("new\nChris Gaeta 96 Lafayette RD, Hampton Falls, NH, 03844\n\nblack chrome",
     {"name": "Chris Gaeta", "city": "Hampton Falls", "state": "NH", "zip": "03844"}),

    # 10. State/zip no space: "Louisiana70570"
    ("BEZY\n710 E Landry St\nOpelousas, Louisiana70570\nMM6 green S",
     {"name": "Bezy", "street": "710 E Landry St", "city": "Opelousas", "state": "LA", "zip": "70570"}),

    # 11. City on own line, state on own line, zip on own line
    ("Nima Sab\n\n2853 Tapo St\nSimi Valley\nCalifornia\n93063\n\nBoth Goyard card",
     {"name": "Nima Sab", "street": "2853 Tapo St", "city": "Simi Valley", "state": "CA", "zip": "93063"}),

    # 12. Trailing comma on CSZ line
    ("Lorenzo Ribadeneira\n336 NE 85th st\nMiami Fl 33138, \n\nBlue Mesh L",
     {"name": "Lorenzo Ribadeneira", "street": "336 Ne 85th St", "city": "Miami", "state": "FL", "zip": "33138"}),

    # 13. "United States" at end
    ("Jonathan Plata\n\n428 W Bringhurst St\nPhiladelphia  PA 19144\nUnited States\n\ntravis scott 9",
     {"name": "Jonathan Plata", "street": "428 W Bringhurst St", "city": "Philadelphia", "state": "PA", "zip": "19144"}),

    # 14. Comma-separated inline with state full name
    ("Cody DeLaet\n4985 Country Park Drive Tipp City Ohio, 45371\nWhite goyard card wallet",
     {"name": "Cody Delaet", "street": "4985 Country Park Drive", "city": "Tipp City", "state": "OH", "zip": "45371"}),

    # 15. Clinton,MD no space after comma
    ("Lo McNeill\n11406 Oscar King Ct\nClinton,MD 20735\nCamo Chrome Hearts cap",
     {"name": "Lo Mcneill", "street": "11406 Oscar King Ct", "city": "Clinton", "state": "MD", "zip": "20735"}),

    # 16. City/state on one line, zip on next (bakersfield)
    ("Andrew Moreno \n434 Lansing Dr \nBakersfield ca\n93309\n\nBlack/black",
     {"name": "Andrew Moreno", "street": "434 Lansing Dr", "city": "Bakersfield", "state": "CA", "zip": "93309"}),

    # 17. Name after address
    ("5401 Spencer Lane\nGranite Bay, CA 95746\n\nGabriel Potter\n\nGold CH logo hat",
     {"name": "Gabriel Potter", "street": "5401 Spencer Lane", "city": "Granite Bay", "state": "CA", "zip": "95746"}),

    # 18. Fully inline with name first, comma separated
    ("Caleb Kersten 17214 Bushmills Rd, Pflugerville, TX, 78660\n\nGreen wallet",
     {"name": "Caleb Kersten", "street": "17214 Bushmills Rd", "city": "Pflugerville", "state": "TX", "zip": "78660"}),

    # 19. Apt on separate line
    ("Jason Salvatierra \n250 Gorge Road\nApt 15H\nCliffside Park, NJ 07010\n\nBlue card wallet",
     {"name": "Jason Salvatierra", "street": "250 Gorge Road", "street2": "Apt 15H", "city": "Cliffside Park", "state": "NJ", "zip": "07010"}),

    # 20. D.C. as state
    ("kendon pegram\n\n3330 4th St SE\nApt 204\nWashington, D.C. 20032\n\nBlack suede 44",
     {"name": "Kendon Pegram", "street": "3330 4th St Se", "street2": "Apt 204", "city": "Washington", "state": "DC", "zip": "20032"}),

    # 21. Full inline with name (no digit start)
    ("Ryan Cu, 10661 La Dona Dr., Garden Grove, CA, 92840\n\nL Grey Henley",
     {"name": "Ryan Cu", "street": "10661 La Dona Dr.", "city": "Garden Grove", "state": "CA", "zip": "92840"}),

    # 22. "Unpaid" noise
    ("Unpaid \nDiego Rosales\n\n132 east county line road Hatboro pa 19040\n\nGreen/Grey ERD S",
     {"name": "Diego Rosales", "street": "132 East County Line Road", "city": "Hatboro", "state": "PA", "zip": "19040"}),

    # 23. Apt with comma inline
    ("Ademola Adewale \n1519 Scripture St, Apt 511B , Denton, TX 76201\n\nBlack stripe S",
     {"name": "Ademola Adewale", "city": "Denton", "state": "TX", "zip": "76201"}),

    # 24. Rhode Island (two-word state)
    ("Jaden Chantavong \n711 dyer ave\nCranston Rhode Island 02920\n\nGreen L long sleeve",
     {"name": "Jaden Chantavong", "street": "711 Dyer Ave", "city": "Cranston", "state": "RI", "zip": "02920"}),

    # 25. ZIP+4
    ("Rogelio Tienda\n101 Webster Rd\nGreensboro NC 27406-6807\nUnited States\n\nacne studios candy chain jeans size 34",
     {"name": "Rogelio Tienda", "street": "101 Webster Rd", "city": "Greensboro", "state": "NC", "zip": "27406-6807"}),

    # 26. Oak Park Michigan , 48237, (spaces around commas, trailing comma on zip)
    ("Brian Morrison\n22156 Marlow St, \nOak Park Michigan , 48237, \nPurple LV Skate size 9",
     {"name": "Brian Morrison", "city": "Oak Park", "state": "MI", "zip": "48237"}),

    # 27. Everything inline, name first (no commas between name and street)
    ("Michael Yambir 6204 cedar ln rowlett tx  75089\n\nBalenciaga",
     {"name": "Michael Yambir", "street": "6204 Cedar Ln", "city": "Rowlett", "state": "TX", "zip": "75089"}),

    # 28. Inline with comma between name parts
    ("Bryce Peters, 3075 104th Ave, Crown Point Indiana, 46307",
     {"name": "Bryce Peters", "city": "Crown Point", "state": "IN", "zip": "46307"}),

    # 29. Unit in street2
    ("Cesar Jimenez\n2230 Morningside Cir\nUnit E\nCarpentersville, Illinois, 60110\n\nERD Yes I Do Believe In God Shirt (Size M)",
     {"name": "Cesar Jimenez", "street": "2230 Morningside Cir", "street2": "Unit E", "city": "Carpentersville", "state": "IL", "zip": "60110"}),

    # 30. Multi-line city/state: "Panama City Fl" on one line, zip on same
    ("Ishmael brown \n1126 louisiana ave\nPanama City Fl 32401\nred chrome hearts long sleeve size s",
     {"name": "Ishmael Brown", "street": "1126 Louisiana Ave", "city": "Panama City", "state": "FL", "zip": "32401"}),

    # 31. Address with "Address:" prefix
    ("Josue Lujan \nAddress:\n2564 S Ensenada Way Aurora Colorado 80013\n\nBlack silver VCA",
     {"name": "Josue Lujan", "street": "2564 S Ensenada Way", "city": "Aurora", "state": "CO", "zip": "80013"}),

    # 32. Single name (one word) "Leviticus"
    ("Leviticus\n1626 NW College Ave\nAnkeny IA 50023\n\nBlack/black hat",
     {"name": "Leviticus", "street": "1626 Nw College Ave", "city": "Ankeny", "state": "IA", "zip": "50023"}),

    # 33. "Forwarded" noise
    ("Forwarded\nBilly Hargrove\n3873 Palmetto Cir\nZionsville IN 46077-8061\nUnited States\nERD belt",
     {"name": "Billy Hargrove", "street": "3873 Palmetto Cir", "city": "Zionsville", "state": "IN", "zip": "46077-8061"}),

    # 34. "apartment" spelled out
    ("Jacobis moon\n204 Windham Rd\nWillimantic,Connecticut,06226\nAcne studio paint black size 29",
     {"name": "Jacobis Moon", "street": "204 Windham Rd", "city": "Willimantic", "state": "CT", "zip": "06226"}),

    # 35. Inline: "Avery B\n4524 Grenadine circle Acworth GA 30101"
    ("Avery B\n4524 Grenadine circle Acworth GA 30101\nChrome heart hat Matty boy",
     {"name": "Avery B", "street": "4524 Grenadine Circle", "city": "Acworth", "state": "GA", "zip": "30101"}),

    # 36. "rj" as name (short), United States at end
    ("rj\n\n16882 Hammon Woods Dr\nHumble, TX  77346\nUnited States\n\nBlack baseball S",
     {"name": "Rj", "street": "16882 Hammon Woods Dr", "city": "Humble", "state": "TX", "zip": "77346"}),

    # 37. Address before name: "2800 Enterprise Road\nApt 1232\nReno Nevada 89512\nAbraham Cuellar"
    ("2800 Enterprise Road \nApt 1232\nReno Nevada 89512\nAbraham Cuellar\n\nWhite CH M",
     {"name": "Abraham Cuellar", "street": "2800 Enterprise Road", "street2": "Apt 1232", "city": "Reno", "state": "NV", "zip": "89512"}),

    # 38. City/state on one line, zip next: "Orlando Fl\n32839"
    ("Christian Everett\n4150 Eastgate Drive apt 7310\nOrlando Fl \n32839\n\nMonogram card holder",
     {"name": "Christian Everett", "city": "Orlando", "state": "FL", "zip": "32839"}),

    # 39. "South Carolina" two-word state
    ("Tony Tinsley\n141 Brookhaven Road\nSummerville, South Carolina, 29486\n\nChrome Hearts Blue L/S ( LARGE )",
     {"name": "Tony Tinsley", "street": "141 Brookhaven Road", "city": "Summerville", "state": "SC", "zip": "29486"}),

    # 40. "Connecticut" full state with commas tight
    ("Jacobis moon\n245 Benham Rd apartment 7\nGroton,Connecticut,06340\nairpods",
     {"name": "Jacobis Moon", "street": "245 Benham Rd", "street2": "Apartment 7", "city": "Groton", "state": "CT", "zip": "06340"}),

    # 41. "Sent" noise, comma in street
    ("Christian Ortiz \n5529 Valley Mills Dr, \nGarland Tx 75043\n\nAirPods",
     {"name": "Christian Ortiz", "city": "Garland", "state": "TX", "zip": "75043"}),

    # 42. Inline name+street: "Promise Agyapong 14847 Dorray Ln Houston Texas 77083"
    ("Promise Agyapong 14847 Dorray Ln Houston Texas 77083\n\nAirPods",
     {"name": "Promise Agyapong", "street": "14847 Dorray Ln", "city": "Houston", "state": "TX", "zip": "77083"}),

    # 43. Multi-line: TX on its own
    ("Ethan Mejia\n350 Las Colinas Blvd E\nAPT 3070\nIrving\nTX\n75039\n\nXXS Lost Tapes",
     {"name": "Ethan Mejia", "street": "350 Las Colinas Blvd E", "street2": "Apt 3070", "city": "Irving", "state": "TX", "zip": "75039"}),

    # 44. Name with comma inline: "Chris Gaeta, 826 S Pecan Pkwy, APT 5204, Justin TX, 76247"
    ("Chris Gaeta, 826 S Pecan Pkwy, APT 5204, Justin TX, 76247\n\nGlasses CH",
     {"name": "Chris Gaeta", "city": "Justin", "state": "TX", "zip": "76247"}),

    # 45. "Wheeling Illinois\n60090" city+state on one line, zip on next
    ("Julian Marsenic \n1802 Avalon drive \nWheeling Illinois \n60090\n\nAirPod pro",
     {"name": "Julian Marsenic", "street": "1802 Avalon Drive", "city": "Wheeling", "state": "IL", "zip": "60090"}),

    # 46. Street with comma then city on next line: "22156 Marlow St,"
    ("Gabriel Lopez\n630 Los Robles Ave., Apt. 14, Palo Alto, CA 94306\n\nRick's",
     {"name": "Gabriel Lopez", "city": "Palo Alto", "state": "CA", "zip": "94306"}),

    # 47. San Juan\nTx\n78589 (city, state, zip all separate lines)
    ("rafael g\n110 miranda lane\nSan Juan\nTx\n78589\n\nL crest zip uo",
     {"name": "Rafael G", "street": "110 Miranda Lane", "city": "San Juan", "state": "TX", "zip": "78589"}),

    # 48. Email in message
    ("Gavin Friel\n82 Broken Bow Lane\nEast Falmouth, Massachusetts \n02536\ngavin.friel.20@gmail.com\n\nblue acne jeans 32",
     {"name": "Gavin Friel", "street": "82 Broken Bow Lane", "city": "East Falmouth", "state": "MA", "zip": "02536"}),

    # 49. "Raytown,Missouri 64138" tight commas
    ("8300 Hawthorne Place\nRaytown,Missouri 64138 \nGio Orozco\n\nAirPod Pro 3's 2x",
     {"name": "Gio Orozco", "street": "8300 Hawthorne Place", "city": "Raytown", "state": "MO", "zip": "64138"}),

    # 50. "Woonsocket Rhode island 02895"
    ("Micah Clemmons \n150 Avenue C \nWoonsocket Rhode island 02895\nAirpod pro 3s",
     {"name": "Micah Clemmons", "street": "150 Avenue C", "city": "Woonsocket", "state": "RI", "zip": "02895"}),
]

passed = 0
failed = 0
for i, (inp, expected) in enumerate(CASES, 1):
    result = parse_address(inp)
    errors = []
    for key, exp_val in expected.items():
        got = result.get(key, "<<MISSING>>")
        if got != exp_val:
            errors.append(f"  {key}: expected {exp_val!r}, got {got!r}")
    if errors:
        failed += 1
        print(f"FAIL #{i}:")
        print(f"  Input: {inp[:80]!r}...")
        for e in errors:
            print(e)
    else:
        passed += 1

print(f"\n{passed} passed, {failed} failed out of {len(CASES)}")
