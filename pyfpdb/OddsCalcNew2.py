from treys import Card
from treys import Evaluator, PLOEvaluator
from treys import Deck


# create a card
card = Card.new('Qh')

# create a board and hole cards
board = [
    Card.new('2h'),
    Card.new('2s'),
    Card.new('Jc'),
    Card.new('4s'),
    Card.new('Kc')
]




# create an evaluator
evaluator = Evaluator()



# or for random cards or games, create a deck
print("Dealing a new hand...")
deck = Deck()

player1_hand = [
    Card.new('Qs'),
    Card.new('Th')
]
player2_hand = [
    Card.new('As'),
    Card.new('Ah')
]

print("The board:")
Card.print_pretty_cards(board)

print("Player 1's cards:")
Card.print_pretty_cards(player1_hand)

print("Player 2's cards:")
Card.print_pretty_cards(player2_hand)

p1_score = evaluator.evaluate(player1_hand, board)
p2_score = evaluator.evaluate(player2_hand, board)

# bin the scores into classes
p1_class = evaluator.get_rank_class(p1_score)
p2_class = evaluator.get_rank_class(p2_score)

# or get a human-friendly string to describe the score
print("Player 1 hand rank = {} {}".format(p1_score, evaluator.class_to_string(p1_class)))
print("Player 2 hand rank = {} {}".format(p2_score, evaluator.class_to_string(p2_class)))

# or just a summary of the entire hand
hands = [player1_hand, player2_hand]
evaluator.hand_summary(board, hands)
