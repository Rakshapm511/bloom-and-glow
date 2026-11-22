
let cart = JSON.parse(localStorage.getItem("bloomCart")) || [];

document.querySelectorAll(".add-cart-btn").forEach(button => {
    button.addEventListener("click", function () {
        const name = this.dataset.name;
        const price = Number(this.dataset.price);
        const image = this.dataset.image;

        const existingProduct = cart.find(item => item.name === name);

        if (existingProduct) {
            existingProduct.quantity++;
        } else {
            cart.push({
                name: name,
                price: price,
                image: image,
                quantity: 1
            });
        }

        localStorage.setItem("bloomCart", JSON.stringify(cart));

        updateCartCount();
    });
});

function updateCartCount() {
    const count = cart.reduce((total, item) => total + item.quantity, 0);

    const cartCount = document.getElementById("cart-count");

    if (cartCount) {
        cartCount.innerText = count;
    }
}

updateCartCount();
