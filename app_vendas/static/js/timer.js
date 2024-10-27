function updateTimer() {
    fetch('/api/time_remaining')
        .then(response => response.json())
        .then(data => {
            const timeElement = document.getElementById('time-remaining');
            timeElement.innerText = data.time_remaining;

            // Se o tempo restante for 0, você pode exibir uma mensagem ou reiniciar o timer
            if (data.time_remaining <= 0) {
                // Aqui você pode fazer algo quando o timer chega a zero, se necessário
            }
        })
        .catch(error => console.error('Erro ao obter o tempo restante:', error));
}

// Iniciar o loop de atualização do timer
setInterval(updateTimer, 1000);

// Função para parar o scheduler
function stopScheduler() {
    window.location.href = '/stop';
}
