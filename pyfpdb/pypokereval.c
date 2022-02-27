/*
 *
 * Copyright (C) 2007, 2008 Loic Dachary <loic@dachary.org>
 * Copyright (C) 2004, 2005, 2006 Mekensleep
 *
 *	Mekensleep
 *	24 rue vieille du temple
 *	75004 Paris
 *       licensing@mekensleep.com
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301, USA.
 *
 * Authors:
 *  Loic Dachary <loic@dachary.org>
 *
 */

#ifdef _DEBUG // for Windows python23_d.lib is not in distribution... ugly but works
 #undef _DEBUG
 #include <Python.h>
 #define _DEBUG
#else
 #include <Python.h>
#endif


/* enumerate.c -- functions to compute pot equity by enumerating outcomes
  Exports:
        enumExhaustive()	exhaustive enumeration of outcomes
        enumGameParams()	look up rule parameters by game type
        enumResultClear()	clear enumeration result object
        enumResultPrint()	print enumeration result object
        enumResultPrintTerse()	print enumeration result object, tersely
        enumSample()		monte carlo sampling of outcomes

   Michael Maurer, Apr 2002
*/

#include "poker_defs.h"
#include "inlines/eval.h"
#include "inlines/eval_low.h"
#include "inlines/eval_low8.h"
#include "inlines/eval_joker_low.h"
#include "inlines/eval_omaha.h"
#include "deck_std.h"
#include "rules_std.h"

#include "enumerate.h"
#include "enumdefs.h"

#ifdef WIN32
#define VERSION_NAME(W) W##2_4
#define PYTHON_VERSION "2_4"
#endif /* WIN32 */

/* INNER_LOOP is executed in every iteration of the combinatorial enumerator
   macros DECK_ENUMERATE_n_CARDS_D() and DECK_ENUMERATE_PERMUTATIONS_D.  It
   evaluates each player's hand based on the enumerated community cards and
   accumulates statistics on wins, ties, losses, and pot equity.

   Macro argument:
   	evalwrap -- code that evaluates pockets[i], board, sharedCards, and/or
        	    unsharedCards[i] as a poker hand, then stores the result
                    in hival[i] and loval[i] and stores an error code in err
   Loop variable: either of
   	StdDeck_CardMask sharedCards;
   	StdDeck_CardMask unsharedCards[];
   Inputs:
   	StdDeck_CardMask pockets[];
        StdDeck_CardMask board;
        int npockets;
   Outputs:
   	enum_result_t *result;
*/

#define INNER_LOOP(evalwrap)						\
    do {								\
      int i;								\
      HandVal hival[ENUM_MAXPLAYERS];					\
      LowHandVal loval[ENUM_MAXPLAYERS];				\
      HandVal besthi = HandVal_NOTHING;					\
      LowHandVal bestlo = LowHandVal_NOTHING;				\
      int hishare = 0;							\
      int loshare = 0;							\
      double hipot, lopot;						\
      /* find winning hands for high and low */				\
      for (i=0; i<sizeToDeal-1; i++) {					\
	int err;							\
        { evalwrap }							\
        if (err != 0)							\
          return 1000 + err;						\
        if (hival[i] != HandVal_NOTHING) {				\
          if (hival[i] > besthi) {					\
            besthi = hival[i];						\
            hishare = 1;						\
          } else if (hival[i] == besthi) {				\
            hishare++;							\
          }								\
        }								\
        if (loval[i] != LowHandVal_NOTHING) {				\
          if (loval[i] < bestlo) {					\
            bestlo = loval[i];						\
            loshare = 1;						\
          } else if (loval[i] == bestlo) {				\
            loshare++;							\
          }								\
        }								\
      }									\
      /* now award pot fractions to winning hands */			\
      if (bestlo != LowHandVal_NOTHING &&				\
          besthi != HandVal_NOTHING) {					\
        hipot = 0.5 / hishare;						\
        lopot = 0.5 / loshare;						\
      } else if (bestlo == LowHandVal_NOTHING &&			\
                 besthi != HandVal_NOTHING) {				\
        hipot = 1.0 / hishare;						\
        lopot = 0;							\
      } else if (bestlo != LowHandVal_NOTHING &&			\
                 besthi == HandVal_NOTHING) {				\
        hipot = 0;							\
        lopot = 1.0 / loshare;						\
      } else {								\
        hipot = lopot = 0;						\
      }									\
      for (i=0; i<sizeToDeal-1; i++) {					\
        double potfrac = 0;						\
        int H = 0, L = 0;						\
        if (hival[i] != HandVal_NOTHING) {				\
          if (hival[i] == besthi) {					\
            H = hishare;						\
            potfrac += hipot;						\
            if (hishare == 1)						\
              result->nwinhi[i]++;					\
             else							\
              result->ntiehi[i]++;					\
          } else {							\
            result->nlosehi[i]++;					\
          }								\
        }								\
        if (loval[i] != LowHandVal_NOTHING) {				\
          if (loval[i] == bestlo) {					\
            L = loshare;						\
            potfrac += lopot;						\
            if (loshare == 1)						\
              result->nwinlo[i]++;					\
            else							\
              result->ntielo[i]++;					\
          } else {							\
            result->nloselo[i]++;					\
          }								\
        }								\
        result->nsharehi[i][H]++;					\
        result->nsharelo[i][L]++;					\
        result->nshare[i][H][L]++;					\
        if (potfrac > 0.99)						\
          result->nscoop[i]++;						\
        result->ev[i] += potfrac;					\
      }									\
      result->nsamples++;						\
    } while (0);

#define INNER_LOOP_ANY_HIGH						\
  INNER_LOOP({								\
    StdDeck_CardMask _hand;						\
    StdDeck_CardMask _finalBoard;					\
    StdDeck_CardMask_RESET(_hand);					\
    StdDeck_CardMask_RESET(_finalBoard);				\
    StdDeck_CardMask_OR(_finalBoard, board, cardsDealt[0]);		\
    StdDeck_CardMask_OR(_hand, pockets[i], _finalBoard);		\
    StdDeck_CardMask_OR(_hand, _hand, cardsDealt[i + 1]);		\
    hival[i] = StdDeck_StdRules_EVAL_N(_hand, 7);			\
    loval[i] = LowHandVal_NOTHING;					\
    err = 0;								\
  })

#define INNER_LOOP_ANY_HILO						\
  INNER_LOOP({								\
    StdDeck_CardMask _hand;						\
    StdDeck_CardMask _finalBoard;					\
    StdDeck_CardMask_RESET(_hand);					\
    StdDeck_CardMask_RESET(_finalBoard);				\
    StdDeck_CardMask_OR(_finalBoard, board, cardsDealt[0]);		\
    StdDeck_CardMask_OR(_hand, pockets[i], _finalBoard);		\
    StdDeck_CardMask_OR(_hand, _hand, cardsDealt[i + 1]);		\
    hival[i] = StdDeck_StdRules_EVAL_N(_hand, 7);			\
    loval[i] = StdDeck_Lowball8_EVAL(_hand, 7);				\
    err = 0;								\
  })

#define INNER_LOOP_OMAHA						\
  INNER_LOOP({								\
    StdDeck_CardMask _hand;						\
    StdDeck_CardMask _finalBoard;					\
    StdDeck_CardMask_RESET(_hand);					\
    StdDeck_CardMask_RESET(_finalBoard);				\
    StdDeck_CardMask_OR(_finalBoard, board, cardsDealt[0]);		\
    StdDeck_CardMask_OR(_hand, pockets[i], cardsDealt[i + 1]);		\
    err = StdDeck_OmahaHiLow8_EVAL(_hand, _finalBoard,                  \
                                   &hival[i], NULL);			\
    loval[i] = LowHandVal_NOTHING;					\
  })

#define INNER_LOOP_OMAHA8						\
  INNER_LOOP({								\
    StdDeck_CardMask _hand;						\
    StdDeck_CardMask _finalBoard;					\
    StdDeck_CardMask_RESET(_hand);					\
    StdDeck_CardMask_RESET(_finalBoard);				\
    StdDeck_CardMask_OR(_finalBoard, board, cardsDealt[0]);		\
    StdDeck_CardMask_OR(_hand, pockets[i], cardsDealt[i + 1]);		\
    err = StdDeck_OmahaHiLow8_EVAL(_hand, _finalBoard,                  \
                                   &hival[i], &loval[i]);		\
  })

#define INNER_LOOP_7STUDNSQ						\
  INNER_LOOP({								\
    StdDeck_CardMask _hand;						\
    StdDeck_CardMask_OR(_hand, pockets[i], cardsDealt[i + 1]);		\
    hival[i] = StdDeck_StdRules_EVAL_N(_hand, 7);			\
    loval[i] = StdDeck_Lowball_EVAL(_hand, 7);				\
    err = 0;								\
  })

#define INNER_LOOP_RAZZ							\
  INNER_LOOP({								\
    StdDeck_CardMask _hand;						\
    StdDeck_CardMask_OR(_hand, pockets[i], cardsDealt[i + 1]);		\
    hival[i] = HandVal_NOTHING;						\
    loval[i] = StdDeck_Lowball_EVAL(_hand, 7);				\
    err = 0;								\
  })

#define INNER_LOOP_5DRAW						\
  INNER_LOOP({								\
    JokerDeck_CardMask _hand;						\
    JokerDeck_CardMask_OR(_hand, pockets[i], cardsDealt[i + 1]);	\
    hival[i] = JokerDeck_JokerRules_EVAL_N(_hand, 5);			\
    loval[i] = LowHandVal_NOTHING;					\
    err = 0;								\
  })

#define INNER_LOOP_5DRAW8						\
  INNER_LOOP({								\
    JokerDeck_CardMask _hand;						\
    JokerDeck_CardMask_OR(_hand, pockets[i], cardsDealt[i + 1]);	\
    hival[i] = JokerDeck_JokerRules_EVAL_N(_hand, 5);			\
    loval[i] = JokerDeck_Lowball8_EVAL(_hand, 5);			\
    err = 0;								\
  })

#define INNER_LOOP_5DRAWNSQ						\
  INNER_LOOP({								\
    JokerDeck_CardMask _hand;						\
    JokerDeck_CardMask_OR(_hand, pockets[i], cardsDealt[i + 1]);	\
    hival[i] = JokerDeck_JokerRules_EVAL_N(_hand, 5);			\
    loval[i] = JokerDeck_Lowball_EVAL(_hand, 5);			\
    err = 0;								\
  })

#define INNER_LOOP_LOWBALL						\
  INNER_LOOP({								\
    JokerDeck_CardMask _hand;						\
    JokerDeck_CardMask_OR(_hand, pockets[i], cardsDealt[i + 1]);	\
    hival[i] = HandVal_NOTHING;						\
    loval[i] = JokerDeck_Lowball_EVAL(_hand, 5);			\
    err = 0;								\
  })

#define INNER_LOOP_LOWBALL27						\
  INNER_LOOP({								\
    StdDeck_CardMask _hand;						\
    StdDeck_CardMask_OR(_hand, pockets[i], cardsDealt[i + 1]);		\
    hival[i] = HandVal_NOTHING;						\
    loval[i] = StdDeck_StdRules_EVAL_N(_hand, 5);			\
    err = 0;								\
  })

static int 
pyenumExhaustive(enum_game_t game, StdDeck_CardMask pockets[],
		 int numToDeal[],
               StdDeck_CardMask board, StdDeck_CardMask dead,
               int sizeToDeal, enum_result_t *result) {
  int totalToDeal = 0;
  int i;
  enumResultClear(result);
  StdDeck_CardMask cardsDealt[ENUM_MAXPLAYERS + 1];
  memset(cardsDealt, 0, sizeof(StdDeck_CardMask) * (ENUM_MAXPLAYERS + 1));
  if (sizeToDeal - 1 > ENUM_MAXPLAYERS)
    return 1;
  for(i = 0; i < sizeToDeal; i++)
    totalToDeal += numToDeal[i];

  /*
   * Cards in pockets or in the board must not be dealt 
   */
  StdDeck_CardMask_OR(dead, dead, board);
  for(i = 0; i < sizeToDeal - 1; i++) {
    StdDeck_CardMask_OR(dead, dead, pockets[i]);
  }

  if (game == game_holdem) {
    if(totalToDeal > 0) {
      DECK_ENUMERATE_COMBINATIONS_D(StdDeck, cardsDealt,
				    sizeToDeal, numToDeal,
				    dead, INNER_LOOP_ANY_HIGH);
    } else {
      INNER_LOOP_ANY_HIGH;
    }
  } else if (game == game_holdem8) {
    if(totalToDeal > 0) {
      DECK_ENUMERATE_COMBINATIONS_D(StdDeck, cardsDealt,
				    sizeToDeal, numToDeal,
				    dead, INNER_LOOP_ANY_HILO);
    } else {
      INNER_LOOP_ANY_HILO;
    }
  } else if (game == game_omaha) {
    if(totalToDeal > 0) {
      DECK_ENUMERATE_COMBINATIONS_D(StdDeck, cardsDealt,
				    sizeToDeal, numToDeal,
				    dead, INNER_LOOP_OMAHA);
    } else {
      INNER_LOOP_OMAHA;
    }
  } else if (game == game_omaha8) {
    if(totalToDeal > 0) {
      DECK_ENUMERATE_COMBINATIONS_D(StdDeck, cardsDealt,
				    sizeToDeal, numToDeal,
				    dead, INNER_LOOP_OMAHA8);
    } else {
      INNER_LOOP_OMAHA8;
    }
  } else if (game == game_7stud) {
    if(totalToDeal > 0) {
      DECK_ENUMERATE_COMBINATIONS_D(StdDeck, cardsDealt,
				    sizeToDeal, numToDeal,
				    dead, INNER_LOOP_ANY_HIGH);
    } else {
      INNER_LOOP_ANY_HIGH;
    }
  } else if (game == game_7stud8) {
    if(totalToDeal > 0) {
      DECK_ENUMERATE_COMBINATIONS_D(StdDeck, cardsDealt,
				    sizeToDeal, numToDeal,
				    dead, INNER_LOOP_ANY_HILO);
    } else {
      INNER_LOOP_ANY_HILO;
    }
  } else if (game == game_7studnsq) {
    DECK_ENUMERATE_COMBINATIONS_D(StdDeck, cardsDealt,
                                  sizeToDeal, numToDeal,
                                  dead, INNER_LOOP_7STUDNSQ);
  } else if (game == game_razz) {
    DECK_ENUMERATE_COMBINATIONS_D(StdDeck, cardsDealt,
                                  sizeToDeal, numToDeal,
                                  dead, INNER_LOOP_RAZZ);
  } else if (game == game_lowball27) {
    DECK_ENUMERATE_COMBINATIONS_D(StdDeck, cardsDealt,
                                  sizeToDeal, numToDeal,
                                  dead, INNER_LOOP_LOWBALL27);
  } else if (game == game_lowball) {
    DECK_ENUMERATE_COMBINATIONS_D(StdDeck, cardsDealt,
                                  sizeToDeal, numToDeal,
                                  dead, INNER_LOOP_LOWBALL);
  } else {
    return 1;
  }

  result->game = game;
  result->nplayers = sizeToDeal - 1;
  result->sampleType = ENUM_EXHAUSTIVE;
  return 0;  
}

static int 
pyenumSample(enum_game_t game, StdDeck_CardMask pockets[],
		 int numToDeal[],
               StdDeck_CardMask board, StdDeck_CardMask dead,
               int sizeToDeal, int iterations, enum_result_t *result) {
  int i;
  enumResultClear(result);
  StdDeck_CardMask cardsDealt[ENUM_MAXPLAYERS + 1];
  memset(cardsDealt, 0, sizeof(StdDeck_CardMask) * (ENUM_MAXPLAYERS + 1));
  if (sizeToDeal - 1 > ENUM_MAXPLAYERS)
    return 1;

  /*
   * Cards in pockets or in the board must not be dealt 
   */
  StdDeck_CardMask_OR(dead, dead, board);
  for(i = 0; i < sizeToDeal - 1; i++) {
    StdDeck_CardMask_OR(dead, dead, pockets[i]);
  }

  if (game == game_holdem) {
    DECK_MONTECARLO_PERMUTATIONS_D(StdDeck, cardsDealt,
				   sizeToDeal, numToDeal,
				   dead, iterations, INNER_LOOP_ANY_HIGH);
  } else if (game == game_holdem8) {
    DECK_MONTECARLO_PERMUTATIONS_D(StdDeck, cardsDealt,
				   sizeToDeal, numToDeal,
				   dead, iterations, INNER_LOOP_ANY_HILO);
  } else if (game == game_omaha) {
    DECK_MONTECARLO_PERMUTATIONS_D(StdDeck, cardsDealt,
				   sizeToDeal, numToDeal,
				   dead, iterations, INNER_LOOP_OMAHA);
  } else if (game == game_omaha8) {
    DECK_MONTECARLO_PERMUTATIONS_D(StdDeck, cardsDealt,
				   sizeToDeal, numToDeal,
				   dead, iterations, INNER_LOOP_OMAHA8);
  } else if (game == game_7stud) {
    DECK_MONTECARLO_PERMUTATIONS_D(StdDeck, cardsDealt,
				   sizeToDeal, numToDeal,
				   dead, iterations, INNER_LOOP_ANY_HIGH);
  } else if (game == game_7stud8) {
    DECK_MONTECARLO_PERMUTATIONS_D(StdDeck, cardsDealt,
				   sizeToDeal, numToDeal,
				   dead, iterations, INNER_LOOP_ANY_HILO);
  } else if (game == game_7studnsq) {
    DECK_MONTECARLO_PERMUTATIONS_D(StdDeck, cardsDealt,
				   sizeToDeal, numToDeal,
				   dead, iterations, INNER_LOOP_7STUDNSQ);
  } else if (game == game_razz) {
    DECK_MONTECARLO_PERMUTATIONS_D(StdDeck, cardsDealt,
				   sizeToDeal, numToDeal,
				   dead, iterations, INNER_LOOP_RAZZ);
  } else if (game == game_lowball27) {
    DECK_MONTECARLO_PERMUTATIONS_D(StdDeck, cardsDealt,
				   sizeToDeal, numToDeal,
				   dead, iterations, INNER_LOOP_LOWBALL27);
  } else if (game == game_lowball) {
    DECK_MONTECARLO_PERMUTATIONS_D(StdDeck, cardsDealt,
				   sizeToDeal, numToDeal,
				   dead, iterations, INNER_LOOP_LOWBALL);
  } else {
    return 1;
  }

  result->game = game;
  result->nplayers = sizeToDeal - 1;
  result->sampleType = ENUM_SAMPLE;
  return 0;  
}

#define NOCARD 255

static int PyList2CardMask(PyObject* object, CardMask* cardsp)
{
  CardMask cards;
  int cards_size = 0;
  int valid_cards_size = 0;

  if(!PyList_Check(object)) {
    PyErr_SetString(PyExc_TypeError, "expected a list of cards");
    return -1;
  }

  valid_cards_size = cards_size = PyList_Size(object);
  CardMask_RESET(cards);

  int card;
  int i;
  for(i = 0; i < cards_size; i++) {
    card = -1;
    PyObject* pycard = PyList_GetItem(object, i);
    if(PyErr_Occurred())
      return -1;

    if(PyString_Check(pycard)) {
      char* card_string = PyString_AsString(pycard);
      if(!strcmp(card_string, "__")) {
	card = 255;
      } else {
	if(Deck_stringToCard(card_string, &card) == 0) {
	  PyErr_Format(PyExc_RuntimeError, "card %s is not a valid card name", card_string);
	  return -1;
	}
      }
    } else if(PyInt_Check(pycard)) {
      card = PyInt_AsLong(pycard);
      if(card != NOCARD && (card < 0 || card > StdDeck_N_CARDS)) {
	PyErr_Format(PyExc_TypeError, "card value (%d) must be in the range [0-%d]", card, StdDeck_N_CARDS);
	return -1;
      }
    } else {
      PyErr_SetString(PyExc_TypeError, "card must be a string or an int");
      return -1;
    }

    if(card == NOCARD)
      valid_cards_size--;
    else
      CardMask_SET(cards, card);
  }

  *cardsp = cards;

  return valid_cards_size;
}

#if 0
static PyObject* CardMask2PyList(CardMask* cardmask)
{
  PyObject* result = 0;
  int cardmask_size = StdDeck_numCards(cardmask);
  int cards[64];
  int i;

  if((i = CurDeck.maskToCards(cardmask, cards)) != cardmask_size) {
    PyErr_Format(PyExc_RuntimeError, "CardMask2PyList: maskToCards returns %d cards, expected %d\n", i, cardmask_size);
    return 0;
  }

  result = PyList_New(0);
  for(i = 0; i < cardmask_size; i++) {
    PyObject* pycard = Py_BuildValue("i", cards[i]);
    int status = PyList_Append(result, pycard);
    Py_DECREF(pycard);
    if(status < 0) return 0;
  }

  return result;
}
#endif

static char doc_poker_evaln[] =
"EvalN";

static PyObject*
poker_evaln(PyObject* self, PyObject *args)
{
  CardMask cards;
  PyObject* pycards;
  HandVal handval;

  if (!PyArg_ParseTuple(args, "O", &pycards))
    return NULL;

  if(PyList2CardMask(pycards, &cards) < 0)
    return NULL;

  handval = Hand_EVAL_N(cards, PyList_Size(pycards));

  return Py_BuildValue("i", handval);
}

static char doc_string2card[] =
"return the numerical representation of a card";

static PyObject*
string2card(PyObject* self, PyObject *args)
{
  char* card_string = 0;

  if (!PyArg_ParseTuple(args, "s", &card_string))
    return NULL;

  {
    int card = 0;

    if(!strcmp(card_string, "__")) {
      card = 255;
    } else {
      if(Deck_stringToCard(card_string, &card) == 0) {
	PyErr_Format(PyExc_RuntimeError, "card %s is not a valid card name", card_string);
	return NULL;
      }
    }

    return Py_BuildValue("b", (unsigned char)card);
  }
}

static char doc_card2string[] =
"return the string representation of a numerical card";

static PyObject*
card2string(PyObject* self, PyObject *args)
{
  int card = 0;

  if (!PyArg_ParseTuple(args, "i", &card))
    return NULL;

  if(card == 255) {
    return Py_BuildValue("s", "__");
  } else {
    /*
     * Avoid using GenericDeck_cardString as long as it insists
     * on using the "static thread" hack (see lib/deck.c).
     */
    char tmp[16];
    StdDeck.cardToString(card, tmp);
    return Py_BuildValue("s", tmp);
  }
}

/*
 * Find the card with highest suit matching rank in hand
 * and remove it from hand. The removed card is returned.
 */
int findanddelete(CardMask* hand, int rank)
{
  int suit;
  for(suit = StdDeck_Suit_LAST; suit >= StdDeck_Suit_FIRST; suit--) {
    int card = StdDeck_MAKE_CARD(rank, suit);
    if(CardMask_CARD_IS_SET(*hand, card)) {
      CardMask_UNSET(*hand, card);
      return card;
    }
  }
  return -1;
}

#define LOWRANK2RANK(c) ((c) == StdDeck_Rank_2 ? StdDeck_Rank_ACE : (c-1))

static PyObject*
CardMask2SortedPyList(CardMask hand, int low)
{
  int i;
  HandVal handval;
  PyObject* result = PyList_New(0);

  if(StdDeck_CardMask_IS_EMPTY(hand)) {
    PyObject* pyvalue = Py_BuildValue("s", "Nothing");
    PyList_Append(result, pyvalue);
    Py_DECREF(pyvalue);
    return result;
  }
  
  if(low) {
    handval = Hand_EVAL_LOW8(hand, 5);
  } else {
    handval = Hand_EVAL_N(hand, 5);
  }

  int htype = HandVal_HANDTYPE(handval);
  {
    PyObject* pyvalue = Py_BuildValue("s", StdRules_handTypeNames[htype]);
    PyList_Append(result, pyvalue);
    Py_DECREF(pyvalue);
  }

  if(!low || htype != LowHandVal_NOTHING) {
    if (StdRules_nSigCards[htype] >= 1) {
      int rank = HandVal_TOP_CARD(handval);
      if(low) rank = LOWRANK2RANK(rank);

      if(htype == HandType_STRAIGHT || htype == HandType_STFLUSH) {
	for(i = rank; rank - i < 5; i--) {
	  int rank_modulo = i < 0 ? StdDeck_Rank_ACE : i;
	  PyObject* pyvalue = Py_BuildValue("i", findanddelete(&hand, rank_modulo));
	  PyList_Append(result, pyvalue);
	  Py_DECREF(pyvalue);
	}
      } else {
	int count;
	switch(htype) {
	case HandType_ONEPAIR:
	case HandType_TWOPAIR:
	  count = 2;
	  break;
	case HandType_TRIPS:
	case HandType_FULLHOUSE:
	  count = 3;
	  break;
	case HandType_QUADS:
	  count = 4;
	  break;
	default:
	  count = 1;
	  break;
	}
	for(i = 0; i < count; i++) {
	  PyObject* pyvalue = Py_BuildValue("i", findanddelete(&hand, rank));
	  PyList_Append(result, pyvalue);
	  Py_DECREF(pyvalue);
	}
      }
    }
    if (StdRules_nSigCards[htype] >= 2) {
      int rank = HandVal_SECOND_CARD(handval);
      int count = 1;
      if(low) rank = LOWRANK2RANK(rank);
      if(htype == HandType_TWOPAIR ||
	 htype == HandType_FULLHOUSE)
	count = 2;

      for(i = 0; i < count; i++) {
	PyObject* pyvalue = Py_BuildValue("i", findanddelete(&hand, rank));
	PyList_Append(result, pyvalue);
	Py_DECREF(pyvalue);
      }
    }    

    if (StdRules_nSigCards[htype] >= 3) {
      int rank = HandVal_THIRD_CARD(handval);
      if(low) rank = LOWRANK2RANK(rank);
      PyObject* pyvalue = Py_BuildValue("i", findanddelete(&hand, rank));
      PyList_Append(result, pyvalue);
      Py_DECREF(pyvalue);
    }

    if (StdRules_nSigCards[htype] >= 4) {
      int rank = HandVal_FOURTH_CARD(handval);
      if(low) rank = LOWRANK2RANK(rank);
      PyObject* pyvalue = Py_BuildValue("i", findanddelete(&hand, rank));
      PyList_Append(result, pyvalue);
      Py_DECREF(pyvalue);
    }

    if (StdRules_nSigCards[htype] >= 5) {
      int rank = HandVal_FIFTH_CARD(handval);
      if(low) rank = LOWRANK2RANK(rank);
      PyObject* pyvalue = Py_BuildValue("i", findanddelete(&hand, rank));
      PyList_Append(result, pyvalue);
      Py_DECREF(pyvalue);
    }

  }

  /*
   * Append remaining cards, highest first
   */
  for(i = Deck_N_CARDS - 1; i >= 0; i--) {
    if (StdDeck_CardMask_CARD_IS_SET(hand, i)) {
      PyObject* pyvalue = Py_BuildValue("i", i);
      PyList_Append(result, pyvalue);
      Py_DECREF(pyvalue);
    }
  }

  return result;
}

/* Evaluate an omaha hand for both high and low.  Return nonzero on error.
   If hival is NULL, skips high evaluation; if loval is NULL, skips
   low evaluation.  Low eval could be sped up with 256x256 rank table. */

static int
OmahaHiLow8_Best(StdDeck_CardMask hole, StdDeck_CardMask board,
		 HandVal *hival, LowHandVal *loval,
		 StdDeck_CardMask *hicards, StdDeck_CardMask *locards) {
  StdDeck_CardMask allcards;
  LowHandVal allval;
  HandVal curhi, besthi;
  LowHandVal curlo, bestlo;
  StdDeck_CardMask hole1[OMAHA_MAXHOLE];
  StdDeck_CardMask board1[OMAHA_MAXBOARD];
  StdDeck_CardMask n1, n2, n3, n4, n5;
  int nhole, nboard;
  int eligible = 0;
  int i, h1, h2, b1, b2, b3;

  /* pluck out individual cards from hole and board masks, save in arrays */
  nhole = nboard = 0;
  for (i=0; i<StdDeck_N_CARDS; i++) {
    if (StdDeck_CardMask_CARD_IS_SET(hole, i)) {
      if (nhole >= OMAHA_MAXHOLE)
        return 1;                               /* too many hole cards */
      StdDeck_CardMask_RESET(hole1[nhole]);
      StdDeck_CardMask_SET(hole1[nhole], i);
      nhole++;
    }
    if (StdDeck_CardMask_CARD_IS_SET(board, i)) {
      if (StdDeck_CardMask_CARD_IS_SET(hole, i)) /* same card in hole and board */
        return 2;
      if (nboard >= OMAHA_MAXBOARD)
        return 3;                               /* too many board cards */
      StdDeck_CardMask_RESET(board1[nboard]);
      StdDeck_CardMask_SET(board1[nboard], i);
      nboard++;
    }
  }

  if (nhole < OMAHA_MINHOLE || nhole > OMAHA_MAXHOLE)
    return 4;                                   /* wrong # of hole cards */
  if (nboard < OMAHA_MINBOARD || nboard > OMAHA_MAXBOARD)
    return 5;                                   /* wrong # of board cards */

  /* quick test in case no low is possible with all 9 cards */
  if (loval != NULL) {
    StdDeck_CardMask_OR(allcards, hole, board);
    allval = StdDeck_Lowball8_EVAL(allcards, nhole + nboard);
    eligible = (allval != LowHandVal_NOTHING);
  }

  /* loop over all combinations of hole with board (60 for 4 hole cards
     and 5 board cards). */
  besthi = HandVal_NOTHING;
  bestlo = LowHandVal_NOTHING;
  /* {h1,h2} loop over all hole card combinations */
  for (h1=0; h1<nhole-1; h1++) {
    StdDeck_CardMask_RESET(n1);
    StdDeck_CardMask_OR(n1, n1, hole1[h1]);
    for (h2=h1+1; h2<nhole; h2++) {
      StdDeck_CardMask_OR(n2, n1, hole1[h2]);
      /* {b1,b2,b3} loop over all board card combinations */
      for (b1=0; b1<nboard-2; b1++) {
        StdDeck_CardMask_OR(n3, n2, board1[b1]);
        for (b2=b1+1; b2<nboard-1; b2++) {
          StdDeck_CardMask_OR(n4, n3, board1[b2]);
          for (b3=b2+1; b3<nboard; b3++) {
            if (hival != NULL) {
              StdDeck_CardMask_OR(n5, n4, board1[b3]);
              curhi = StdDeck_StdRules_EVAL_N(n5, 5);
              if (curhi > besthi || besthi == HandVal_NOTHING) {
                besthi = curhi;
		*hicards = n5;
	      }
            }
            if (loval != NULL && eligible) {
              curlo = StdDeck_Lowball8_EVAL(n5, 5);
              if (curlo < bestlo || bestlo == LowHandVal_NOTHING) {
                bestlo = curlo;
		*locards = n5;
	      }
            }
          }
        }
      }
    }
  }
  if (hival != NULL) *hival = besthi;
  if (loval != NULL) *loval = bestlo;
  return 0;
}

static char doc_eval_hand[] = 
"return the evaluation of the hand, either low or hi. Result is a list, first element hand value, second element the best 5 card hand as a list of card values.";

static PyObject*
eval_hand(PyObject* self, PyObject *args)
{
  PyObject* result = 0;
  char* hilow_string = 0;
  PyObject* pyhand = 0;
  PyObject* pyboard = 0;
  int low = 0;
  CardMask hand;
  CardMask board;
  int board_size = 0;
  CardMask best;
  HandVal best_handval;

  StdDeck_CardMask_RESET(best);

  if (!PyArg_ParseTuple(args, "sOO", &hilow_string, &pyhand, &pyboard))
    return NULL; 

  if(!strcmp(hilow_string, "low"))
    low = 1;

  if(PyList2CardMask(pyhand, &hand) < 0)
    return NULL;

  board_size = PyList2CardMask(pyboard, &board);

  if(board_size > 0) {
    CardMask hicards;
    CardMask locards;
    HandVal  hival = 0;
    HandVal  loval = 0;
    StdDeck_CardMask_RESET(hicards);
    StdDeck_CardMask_RESET(locards);
    OmahaHiLow8_Best(hand, board, &hival, &loval, &hicards, &locards);
    if(low) {
      best_handval = loval;
      if(best_handval != LowHandVal_NOTHING)
	best = locards;
    } else {
      best = hicards;
      best_handval = hival;
    }
  } else {
    CardMask cards;
    CardMask dead;

    StdDeck_CardMask_RESET(best);

    StdDeck_CardMask_RESET(dead);
    StdDeck_CardMask_OR(dead, dead, hand);
    StdDeck_CardMask_NOT(dead, dead);

    if(low) {
      best_handval = LowHandVal_NOTHING;
    } else {
      best_handval = HandVal_NOTHING;
    }

    ENUMERATE_N_CARDS_D(cards, 5, dead, 
    {
      HandVal handval;

      if(low) {
	handval = Hand_EVAL_LOW8(cards, 5);
      } else {
	handval = Hand_EVAL_N(cards, 5);
      }

      if(low ? (handval < best_handval) : (handval > best_handval)) {
	best = cards;
	best_handval = handval;
      }
    }
			);
  }

  if(StdDeck_CardMask_IS_EMPTY(best)) {
    best_handval = low ? 0x0FFFFFFF : 0;
  }

  result = PyList_New(0);
  {
    PyObject* pyvalue = Py_BuildValue("i", best_handval);
    PyList_Append(result, pyvalue);
    Py_DECREF(pyvalue);
  }
  {
    PyObject* pyvalue = CardMask2SortedPyList(best, low);
    PyList_Append(result, pyvalue);
    Py_DECREF(pyvalue);
  }
  return result;
}

static char doc_poker_eval[] = 
"eval a poker game state";

static PyObject*
poker_eval(PyObject* self, PyObject *args, PyObject *keywds)
{
  int i;
  int pockets_size;
  int fill_pockets = 0;
  int iterations = 0;
  PyObject* pypockets = 0;
  PyObject* pyboard = 0;
  char* game = 0;
  PyObject* pydead = 0;
  enum_gameparams_t* params = 0;

  StdDeck_CardMask pockets[ENUM_MAXPLAYERS];
  int numToDeal[ENUM_MAXPLAYERS];
  CardMask dead_cards;
  CardMask board_cards;

  PyObject* result = NULL;

  static char *kwlist[] = {"game", "pockets", "board", "dead", "fill_pockets", "iterations", NULL};

  if (!PyArg_ParseTupleAndKeywords(args, keywds, "sOO|Oii", kwlist, 
				   &game, &pypockets, &pyboard, &pydead, &fill_pockets, &iterations))
    return NULL; 

  if(!strcmp(game, "holdem")) {
    params = enumGameParams(game_holdem);
  } else if(!strcmp(game, "holdem8")) {
    params = enumGameParams(game_holdem8);
  } else if(!strcmp(game, "omaha")) {
    params = enumGameParams(game_omaha);
  } else if(!strcmp(game, "omaha8")) {
    params = enumGameParams(game_omaha8);
  } else if(!strcmp(game, "7stud")) {
    params = enumGameParams(game_7stud);
  } else if(!strcmp(game, "7stud8")) {
    params = enumGameParams(game_7stud8);
  } else if(!strcmp(game, "7studnsq")) {
    params = enumGameParams(game_7studnsq);
  } else if(!strcmp(game, "razz")) {
    params = enumGameParams(game_razz);
  } else if(!strcmp(game, "5draw")) {
    params = enumGameParams(game_5draw);
  } else if(!strcmp(game, "5draw8")) {
    params = enumGameParams(game_5draw8);
  } else if(!strcmp(game, "5drawnsq")) {
    params = enumGameParams(game_5drawnsq);
  } else if(!strcmp(game, "lowball")) {
    params = enumGameParams(game_lowball);
  } else if(!strcmp(game, "lowball27")) {
    params = enumGameParams(game_lowball27);
  }
  if(params == 0) {
    PyErr_Format(PyExc_RuntimeError, "game %s is not a valid value (holdem, holdem8, omaha, omaha8, 7stud, 7stud8, 7studnsq, razz, 5draw, 5draw8, 5drawnsq, lowball, lowball27)", game);
  }

  if(!PyList_Check(pypockets)) {
    PyErr_SetString(PyExc_TypeError, "pockets must be list");
    goto err;
  }

  pockets_size = PyList_Size(pypockets);

  {
    for(i = 0; i < pockets_size; i++) {
      int count;
      CardMask_RESET(pockets[i]);
      PyObject* pypocket = PyList_GetItem(pypockets, i);
      if(PyErr_Occurred()) 
	goto err;

      count = PyList2CardMask(pypocket, &pockets[i]);
      if(count < 0)
	goto err;
      if(count < PyList_Size(pypocket))
	numToDeal[i + 1] = PyList_Size(pypocket) - count;
      else
	numToDeal[i + 1] = 0;
    }
  }

  {
    int count;
    count = PyList2CardMask(pyboard, &board_cards);
    if(count < 0)
      goto err;
    if(count < PyList_Size(pyboard))
      numToDeal[0] = PyList_Size(pyboard) - count;
    else
      numToDeal[0] = 0;
  }

  if(pydead) {
    if(PyList2CardMask(pydead, &dead_cards) < 0)
      goto err;
  } else {
    CardMask_RESET(dead_cards);
  }

  {
    enum_result_t cresult;
    int err;
    memset(&cresult, '\0', sizeof(enum_result_t));

    if(iterations > 0) {
      err = pyenumSample(params->game, pockets, numToDeal, board_cards, dead_cards, pockets_size + 1, iterations, &cresult);
    } else {
      err = pyenumExhaustive(params->game, pockets, numToDeal, board_cards, dead_cards, pockets_size + 1, &cresult);
    }
    if(err != 0) {
      PyErr_Format(PyExc_RuntimeError, "poker-eval: pyenum returned error code %d", err);
      return 0;
    }

    result = PyList_New(0);

    PyObject* tmp;
    tmp = Py_BuildValue("(iii)", cresult.nsamples, params->haslopot, params->hashipot);
    PyList_Append(result, tmp);
    Py_DECREF(tmp);
    for(i = 0; i < pockets_size; i++) {
      tmp = Py_BuildValue("(iiiiiiid)",
			  cresult.nscoop[i],
			  cresult.nwinhi[i],
			  cresult.nlosehi[i],
			  cresult.ntiehi[i],
			  cresult.nwinlo[i],
			  cresult.nloselo[i],
			  cresult.ntielo[i],
			  cresult.ev[i] / cresult.nsamples);
      PyList_Append(result, tmp);
      Py_DECREF(tmp);
    }
  }

err:
  return result;
}

static PyMethodDef base_methods[] = {
  { "eval_hand", (PyCFunction)eval_hand, METH_VARARGS | METH_KEYWORDS, doc_eval_hand },
  { "poker_eval", (PyCFunction)poker_eval, METH_VARARGS | METH_KEYWORDS, doc_poker_eval },
  { "evaln", (PyCFunction)poker_evaln, METH_VARARGS, doc_poker_evaln },
  { "string2card", (PyCFunction)string2card, METH_VARARGS, doc_string2card },
  { "card2string", (PyCFunction)card2string, METH_VARARGS, doc_card2string },
  {NULL, NULL, 0, NULL}
};

#ifdef __cplusplus
extern "C" {
#endif
DL_EXPORT(void)
VERSION_NAME(init_pokereval_)(void)
{
  Py_InitModule("_pokereval_" PYTHON_VERSION , base_methods);
}
#ifdef __cplusplus
}
#endif
