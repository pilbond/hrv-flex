1. acute_load_72h_rel  
    Quiere capturar cuánta carga reciente traes respecto a tu normal actual, no respecto a un número fijo.  
    Ejemplo: 180 puntos en 3 días pueden ser muchísimo en una fase de baja carga y completamente normales en una fase de volumen.  
    Se calcularía como el percentil o z-score de la suma de load_day de t-1 a t-3 contra tus últimas 6-8 semanas.  
    Mejora la app porque sustituye reglas muertas como load_3d > 250 por una señal personalizada. El usuario dejaría de recibir avisos basados en umbrales pensados para “un atleta genérico”.
    
2. quality_stress_72h  
    Quiere capturar el coste autonómico de la intensidad reciente.  
    La HRV suele reaccionar más a 2 días con tempo/intervalos/fuerza dura que a varias horas suaves. Por eso no basta con mirar carga total.  
    Se calcularía con work_total_min_day, z3_min_day y, si el dato es fiable, late_intensity_day.  
    Ejemplo simple: quality_stress_72h = minutos de trabajo + peso extra para Z3 y para intensidad tardía.  
    Mejora la app porque permite distinguir “he entrenado mucho” de “he metido estrés de calidad que probablemente sí afecte a la HRV de mañana”.
    
3. hard_day_stack_4d  
    Quiere capturar si estás apilando días exigentes sin dar hueco de absorción.  
    Tres días medio-duros seguidos suelen castigar más que la misma carga repartida con un día fácil entre medias.  
    Se calcularía contando cuántos de los últimos 4 días fueron “duros” para ti, usando percentiles propios, por ejemplo load_day > p66 o quality_stress > p80.  
    Mejora la app porque introduce algo que hoy no ve: la distribución de la carga. La fisiología responde mucho a cómo se reparte el estrés, no solo a cuánto suma.
    
4. acute_chronic_ratio_7_28  
    Quiere capturar si hay un pico de carga respecto a tu capacidad reciente.  
    No es lo mismo pasar de 60 a 100 que de 140 a 180. El número absoluto puede ser menor, pero el salto relativo puede ser mucho más agresivo.  
    Se calcularía como la relación entre la carga aguda de 7 días y la crónica de 28 días.  
    Mejora la app porque detecta spikes, que suelen ser más peligrosos que la carga alta sostenida pero estable. Esto ayuda mucho en semanas donde el gate aún sale verde pero la progresión se está volviendo arriesgada.
    
5. monotony_7d  
    Quiere capturar fatiga por repetición sin variabilidad.  
    Dos semanas con el mismo volumen total no son equivalentes: una con días ligeros y otra con todos los días “medianamente duros” no dejan el mismo coste.  
    Se calcularía como media de la carga 7d / desviación estándar 7d. Si todo se parece demasiado, la monotonía sube.  
    Mejora la app porque detecta desgaste plano, el típico estado en que no explotas en un día concreto, pero el sistema nervioso se va apagando poco a poco.
    

**Qué quieren capturar en conjunto**  
Estas 5 métricas miran la carga desde 5 ángulos distintos:

- acute_load_72h_rel: cantidad reciente
- quality_stress_72h: calidad reciente
- hard_day_stack_4d: densidad del estrés
- acute_chronic_ratio_7_28: pico respecto a capacidad
- monotony_7d: repetición sin descarga

Eso mejora la app porque hoy la pregunta implícita es demasiado simple: “¿hubo mucha carga?”. La pregunta correcta es: ¿hubo un tipo de carga, en una densidad y en un contexto, que haga esperable peor recuperación mañana?

**Cómo mejoraría la app en la práctica**

- Haría que reason_text fuese mucho más útil. En vez de “carga acumulada alta”, podría decir “3 días duros seguidos” o “pico agudo 7d vs 28d”.
- Reduciría falsos mensajes vacíos. Ahora varios umbrales casi no saltan nunca.
- Permitiría una ACTION más fina sin tocar el gate base. Ejemplo: gate verde + acute_chronic alto + hard_day_stack alto = mantener calidad, pero no progresar.
- Haría el sistema más personal. La misma carga no significa lo mismo en agosto que en enero.
- Ayudaría a detectar riesgo cuando la HRV todavía no ha colapsado, que es donde más valor da una app de decisión.

**Lo importante**  
Yo no metería estas métricas directamente en el color del gate todavía. Las usaría así:

1. Primero en logging-only y reason_text.
2. Luego en ACTION, como limitador suave.
3. Solo si demuestran valor predictivo, pasar alguna al decisor.

Eso es exactamente lo que mejoraría la app: no haría el semáforo más “ruidoso”, lo haría más inteligente y explicativo.