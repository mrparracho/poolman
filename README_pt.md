# **Abordagem Científica para a Seleção de Pools de Liquidez na Rede Solana**


---

## **1. Introdução**  

A crescente adoção de Finanças Descentralizadas (DeFi) tem transformado a forma como os investidores gerem a sua liquidez e obtêm rendimento passivo através de pools de liquidez (LPs). No entanto, a escolha de uma pool eficiente para maximizar retornos enquanto se minimiza o risco continua a ser um desafio significativo.  

Este documento apresenta um modelo quantitativo para a seleção de pools de liquidez na rede **Solana**, utilizando métricas chave como **volume de negociação, liquidez e volatilidade**. A abordagem proposta combina análise estatística e modelos de decisão para otimizar a alocação de fundos em pools que oferecem **alta rentabilidade e baixa exposição ao risco**.

O objetivo central é desenvolver uma estratégia baseada em dados que permita aos investidores:
- Selecionar pools de liquidez com **potencial de rentabilidade superior**.
- Minimizar perdas associadas à **impermanent loss** e baixa liquidez.
- Criar uma abordagem **automatizada e replicável** para a gestão de liquidez.

A metodologia adotada baseia-se numa **média ponderada de métricas** para avaliar as LPs de forma objetiva. Para validar a eficácia do modelo, aplicamos **backtesting** em períodos históricos de diferentes condições de mercado, comparando os resultados com estratégias tradicionais.

Nos capítulos seguintes, exploramos os critérios de seleção, a estrutura matemática da análise, a fórmula de avaliação das pools e o processo de validação do modelo.  

---

## **2. Critérios de Seleção da Pool**  

A escolha de uma pool de liquidez eficiente depende da combinação de três fatores principais: **volume de negociação, liquidez total e volatilidade**. Estes indicadores permitem identificar pools que maximizam o retorno com menor risco.

### **2.1 Volume de Negociação**  
O **volume de negociação diário** de uma pool representa a quantidade de transações que ocorrem dentro dela. Um volume elevado indica **alta atividade de traders**, o que leva a um maior número de taxas geradas para os provedores de liquidez.  

A seleção da pool deve considerar:  
- **Média móvel do volume diário** nos últimos *X* períodos.  
- **Relação volume/liquidez**, para evitar pools com volume baixo relativo à liquidez total.  
- **Consistência do volume** ao longo do tempo, evitando pools com picos esporádicos.  

A fórmula utilizada para o cálculo do volume médio ponderado:  

$$ V_{med} = \frac{\sum_{t=1}^{n} V_t w_t}{\sum_{t=1}^{n} w_t} $$

onde:
- $V_t$ é o volume de negociação na unidade de tempo $t$
- $w_t$ é o peso atribuído a cada período (ex: ponderação maior para períodos mais recentes)
- $n$ representa o número total de períodos analisados

---

### **2.2 Liquidez da Pool**  
A liquidez total de uma pool determina a sua capacidade de suportar grandes volumes de negociação sem causar **slippage excessivo**. Pools com maior liquidez são mais estáveis e menos propensas a flutuações de preço inesperadas.  

Os principais fatores avaliados na liquidez são:  
- **Total Value Locked (TVL):** Representa o montante total depositado na pool.  
- **Relação Volume/TVL:** Se o volume de negociação for muito baixo em relação ao TVL, o retorno em taxas pode ser reduzido.  
- **Distribuição da liquidez:** Pools concentradas em certos ranges de preço podem ser mais eficientes para estratégias específicas.  

A métrica de eficiência da liquidez pode ser expressa por:
$$ L_{eff} = \frac{V_{med}}{TVL} $$

Onde um valor **mais elevado** de $L_{eff}$ indica uma pool mais eficiente em gerar retornos com base na liquidez alocada.

---

### **2.3 Volatilidade**  
A volatilidade mede a variação do preço dos ativos dentro da pool, influenciando diretamente o risco de **impermanent loss**. Para avaliar a volatilidade, utilizamos:  

- **Average True Range (ATR)**: Mede a amplitude média das variações de preço.  
- **Desvio Padrão dos preços**: Indica a dispersão dos retornos da pool.  
- **Bollinger Bands**: Identifica momentos de alta ou baixa volatilidade.  

A fórmula para o **ATR** é:

$$ ATR_n = \frac{1}{n} \sum_{t=1}^{n} TR_t $$

Onde $TR_t$ (True Range) é calculado como:

$$ TR_t = \max (H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|) $$

onde:
- $H_t$ e $L_t$ são o preço máximo e mínimo do ativo no período $t$.
- $C_{t-1}$ é o preço de fecho do período anterior.

Já o **desvio padrão ($\sigma$)** dos retornos é dado por:

$$ \sigma = \sqrt{\frac{1}{n} \sum_{t=1}^{n} (r_t - \bar{r})^2} $$

Onde:
- $r_t$ é o retorno do ativo no período $t$.
- $\bar{r}$ é o retorno médio nos últimos $n$ períodos.

Uma volatilidade **moderada** pode ser benéfica, pois impulsiona as taxas geradas, enquanto uma volatilidade extrema aumenta o risco de perda.

---

## **3. Média Ponderada**  

A avaliação final de cada pool é feita através de uma **média ponderada** das três métricas principais:

$$ S = w_1 V_{med} + w_2 L_{eff} + w_3 \frac{1}{\sigma} $$

onde:
- $w_1, w_2, w_3$ são os pesos atribuídos a cada critério.
- **$V_{med}$** representa o volume médio ponderado.
- **$L_{eff}$** é a eficiência da liquidez.
- **$\frac{1}{\sigma}$** penaliza pools com alta volatilidade.

Os pesos podem ser ajustados conforme o perfil de risco do investidor. Por exemplo, para estratégias mais conservadoras, o peso da volatilidade ($w_3$) pode ser aumentado para priorizar pools mais estáveis.

---

## **4. Backtesting**  

Para validar a estratégia, realizamos um **backtesting** utilizando dados históricos das principais pools da **Solana (Raydium, Orca, Jupiter)**. O processo envolve:  

1. **Coleta de dados históricos**: Volume, TVL e preços dos ativos.  
2. **Cálculo das métricas**: Volume médio, eficiência da liquidez e volatilidade.  
3. **Aplicação da fórmula ponderada** para classificar pools.  
4. **Comparação com estratégias tradicionais**: Medimos os retornos obtidos pelas pools selecionadas vs. um portfólio aleatório.  

Os resultados demonstram que o modelo **supera estratégias convencionais** ao evitar pools com baixa liquidez e alta volatilidade excessiva.

---

## **5. Conclusão**  

Este whitepaper propõe uma abordagem quantitativa para a seleção de pools de liquidez na rede **Solana**, combinando **volume, liquidez e volatilidade** numa métrica ponderada. A metodologia permite identificar pools que maximizam retornos enquanto mitigam riscos.  

Os próximos passos incluem:
- **Automatização do processo** com um AI Agent para execução em tempo real.
- **Testes adicionais em diferentes condições de mercado**.
- **Expansão para outras redes DeFi além da Solana**.

Este modelo representa uma solução escalável para investidores que procuram **otimizar a gestão da sua liquidez no DeFi**.


