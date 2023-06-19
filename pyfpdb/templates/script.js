// This function will be executed when the DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Add any JavaScript logic here

    // Example: Display an alert when a card is clicked
    var cards = document.getElementsByClassName('card');
    for (var i = 0; i < cards.length; i++) {
        cards[i].addEventListener('click', function() {
            alert('Card clicked: ' + this.innerText);
        });
    }
});