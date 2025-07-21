if quantity <= 0:
                self.logger.warning("⚠️ No se puede calcular tamaño de posición válido")
                return False
            
            stop_price = price * (1 + self.stop_loss_pct / 100)
            take_profit_price = price * (1 - self.take_profit_pct / 100)
            
            try:
                if self.testnet:
                    order = self.exchange.create_market_order(self.symbol, 'sell', quantity)
                else:
                    order = self.exchange.create_market_order(self.symbol, 'sell', quantity)
            except Exception as order_error:
                self.logger.warning(f"Error creando orden real: {order_error}")
                order = self.create_test_order('sell', quantity, price)
            
            self.position = {
                'side': 'short',
                'entry_price': price,
                'entry_time': datetime.now(),
                'quantity': quantity,
                'stop_loss': stop_price,
                'take_profit': take_profit_price,
                'order_id': order['id'],
                'entry_rsi': rsi,
                'entry_confidence': self.signal_confidence,
                'entry_ema_fast': ema_fast,
                'entry_ema_slow': ema_slow,
                'entry_ema_trend': ema_trend,
                'entry_trend_direction': trend_direction,
                'entry_volatility': volatility,
                'entry_market_regime': market_data['market_regime'],
                'confirmation_time': confirmation_time,
                'recovered': False,
                'lowest_price': price,
                'trailing_stop': stop_price,
                'breakeven_moved': False
            }
            
            self.in_position = True
            
            self.logger.info(f"🔴 SHORT OPTIMIZADO EJECUTADO: {quantity:.6f} BTC @ ${price:.2f}")
            self.logger.info(f"📊 SL: ${stop_price:.2f} | TP: ${take_profit_price:.2f} | Confianza: {self.signal_confidence:.2f}")
            self.logger.info(f"🔄 Tendencia: {trend_direction} | RSI: {rsi:.1f} | Volatilidad: {volatility:.1f}%")
            self.logger.info(f"💰 Tamaño dinámico: {(quantity * price):.2f} USDT ({((quantity * price) / self.get_account_balance()) * 100:.1f}%)")
            
            self.log_trade('OPEN', 'short', price, quantity, rsi, ema_fast, ema_slow, ema_trend,
                          trend_direction, 'Optimized Short Entry', confirmation_time=confirmation_time,
                          confidence=self.signal_confidence, market_regime=market_data['market_regime'],
                          volatility=volatility)
            
            self.save_bot_state()
            return True
            
        except Exception as e:
            self.logger.error(f"Error abriendo posición SHORT: {e}")
            return False
    
    def close_position(self, reason="Manual", current_rsi=None, current_price=None, market_data=None):
        """Cierra la posición actual"""
        if not self.in_position or not self.position:
            return
            
        try:
            side = 'sell' if self.position['side'] == 'long' else 'buy'
            
            # Obtener precio actual si no se proporciona
            if current_price is None:
                ticker = self.exchange.fetch_ticker(self.symbol)
                current_price = ticker['last']
            
            # Intentar crear orden de cierre
            try:
                order = self.exchange.create_market_order(self.symbol, side, self.position['quantity'])
            except Exception as order_error:
                self.logger.warning(f"Error creando orden de cierre: {order_error}")
                order = self.create_test_order(side, self.position['quantity'], current_price)
            
            # Calcular P&L
            if self.position['side'] == 'long':
                pnl_pct = ((current_price - self.position['entry_price']) / self.position['entry_price']) * 100
            else:
                pnl_pct = ((self.position['entry_price'] - current_price) / self.position['entry_price']) * 100
            
            pnl_pct *= self.leverage
            
            # Calcular duración del swing
            duration_hours = (datetime.now() - self.position['entry_time']).total_seconds() / 3600
            
            # Determinar si fue ganancia o pérdida
            if pnl_pct > 0:
                result_emoji = "💚"
                result_text = "GANANCIA"
            else:
                result_emoji = "💔"
                result_text = "PÉRDIDA"
            
            self.logger.info(f"⭕ Posición OPTIMIZADA cerrada - {reason}")
            self.logger.info(f"{result_emoji} {result_text}: {pnl_pct:+.2f}% | Duración: {duration_hours:.1f}h")
            self.logger.info(f"📊 Confianza entrada: {self.position.get('entry_confidence', 0):.2f} | Régimen: {self.position.get('entry_market_regime', 'unknown')}")
            
            # Log detallado del cierre
            ema_data = market_data if market_data else {}
            self.log_trade('CLOSE', self.position['side'], current_price, 
                          self.position['quantity'], current_rsi, 
                          ema_data.get('ema_fast', 0), ema_data.get('ema_slow', 0), 
                          ema_data.get('ema_trend', 0), ema_data.get('trend_direction', 'unknown'),
                          reason, pnl_pct, duration_hours,
                          confidence=self.position.get('entry_confidence', 0),
                          market_regime=ema_data.get('market_regime', 'unknown'),
                          volatility=ema_data.get('volatility', 0))
            
            self.position = None
            self.in_position = False
            
            self.save_bot_state()
            return True
            
        except Exception as e:
            self.logger.error(f"Error cerrando posición: {e}")
            return False
    
    def update_trailing_stop_optimized(self, current_price, market_data):
        """Sistema de trailing stop optimizado"""
        if not self.in_position or not self.position:
            return
        
        volatility = market_data.get('volatility', 1.0)
        
        # Ajustar distancia del trailing stop basado en volatilidad
        dynamic_trailing_distance = self.trailing_stop_distance
        if volatility > 3.0:  # Alta volatilidad
            dynamic_trailing_distance *= 1.5
        elif volatility < 1.0:  # Baja volatilidad
            dynamic_trailing_distance *= 0.8
        
        if self.position['side'] == 'long':
            # Actualizar precio máximo
            if current_price > self.position['highest_price']:
                self.position['highest_price'] = current_price
                
                # Mover stop loss a breakeven cuando ganemos el threshold
                if not self.position['breakeven_moved']:
                    gain_pct = ((current_price - self.position['entry_price']) / self.position['entry_price']) * 100
                    if gain_pct >= self.breakeven_threshold:
                        self.position['trailing_stop'] = self.position['entry_price'] * 1.002  # Breakeven + 0.2%
                        self.position['breakeven_moved'] = True
                        self.logger.info(f"🔒 Stop movido a BREAKEVEN: ${self.position['trailing_stop']:.2f} (ganancia: {gain_pct:.1f}%)")
                        return
                
                # Trailing stop normal (solo si ya está en breakeven)
                if self.position['breakeven_moved']:
                    new_trailing_stop = current_price * (1 - dynamic_trailing_distance / 100)
                    if new_trailing_stop > self.position['trailing_stop']:
                        old_stop = self.position['trailing_stop']
                        self.position['trailing_stop'] = new_trailing_stop
                        gain_from_entry = ((current_price - self.position['entry_price']) / self.position['entry_price']) * 100
                        self.logger.info(f"📈 Trailing Stop: ${old_stop:.2f} → ${new_trailing_stop:.2f} | Ganancia: {gain_from_entry:.1f}%")
                        
        else:  # SHORT
            if current_price < self.position['lowest_price']:
                self.position['lowest_price'] = current_price
                
                if not self.position['breakeven_moved']:
                    gain_pct = ((self.position['entry_price'] - current_price) / self.position['entry_price']) * 100
                    if gain_pct >= self.breakeven_threshold:
                        self.position['trailing_stop'] = self.position['entry_price'] * 0.998  # Breakeven - 0.2%
                        self.position['breakeven_moved'] = True
                        self.logger.info(f"🔒 Stop movido a BREAKEVEN: ${self.position['trailing_stop']:.2f} (ganancia: {gain_pct:.1f}%)")
                        return
                
                if self.position['breakeven_moved']:
                    new_trailing_stop = current_price * (1 + dynamic_trailing_distance / 100)
                    if new_trailing_stop < self.position['trailing_stop']:
                        old_stop = self.position['trailing_stop']
                        self.position['trailing_stop'] = new_trailing_stop
                        gain_from_entry = ((self.position['entry_price'] - current_price) / self.position['entry_price']) * 100
                        self.logger.info(f"📉 Trailing Stop: ${old_stop:.2f} → ${new_trailing_stop:.2f} | Ganancia: {gain_from_entry:.1f}%")
    
    def check_exit_conditions_optimized(self, current_price, current_rsi, market_data):
        """Condiciones de salida optimizadas"""
        if not self.in_position or not self.position:
            return
        
        # Actualizar trailing stop
        self.update_trailing_stop_optimized(current_price, market_data)
        
        trend_direction = market_data.get('trend_direction', 'neutral')
        ema_fast = market_data.get('ema_fast', 0)
        ema_slow = market_data.get('ema_slow', 0)
        volatility = market_data.get('volatility', 1.0)
        market_regime = market_data.get('market_regime', 'trending')
        
        if self.position['side'] == 'long':
            # 1. Stop Loss de emergencia
            if current_price <= self.position['stop_loss']:
                self.close_position("Stop Loss Emergencia", current_rsi, current_price, market_data)
                return
            
            # 2. Take Profit objetivo
            elif current_price >= self.position['take_profit']:
                self.close_position("Take Profit Objetivo", current_rsi, current_price, market_data)
                return
            
            # 3. Trailing stop dinámico
            elif current_price <= self.position['trailing_stop']:
                price_from_max = ((self.position['highest_price'] - current_price) / self.position['highest_price']) * 100
                self.close_position(f"Trailing Stop (-{price_from_max:.1f}%)", current_rsi, current_price, market_data)
                return
            
            # 4. Salida por cambio de régimen de mercado
            elif (market_regime == 'volatile' and volatility > 4.0 and 
                  self.position.get('entry_market_regime') != 'volatile'):
                self.close_position("Mercado muy volátil", current_rsi, current_price, market_data)
                return
            
            # 5. Cambio de tendencia a bajista (solo con confirmaciones adicionales)
            elif trend_direction == 'bearish':
                # Solo salir si también hay señales técnicas adversas
                if current_rsi > 70 or current_price < ema_fast:
                    self.close_position("Tendencia bajista + señales adversas", current_rsi, current_price, market_data)
                    return
                else:
                    self.logger.warning("⚠️ Tendencia bajista detectada pero manteniendo posición (sin señales adversas)")
            
            # 6. RSI extremadamente overbought + precio bajo EMA21
            elif current_rsi > 80 and current_price < ema_fast:
                self.close_position("RSI extremo + ruptura EMA21", current_rsi, current_price, market_data)
                return
                
        else:  # SHORT
            # 1. Stop Loss de emergencia
            if current_price >= self.position['stop_loss']:
                self.close_position("Stop Loss Emergencia", current_rsi, current_price, market_data)
                return
            
            # 2. Take Profit objetivo
            elif current_price <= self.position['take_profit']:
                self.close_position("Take Profit Objetivo", current_rsi, current_price, market_data)
                return
            
            # 3. Trailing stop dinámico
            elif current_price >= self.position['trailing_stop']:
                price_from_min = ((current_price - self.position['lowest_price']) / self.position['lowest_price']) * 100
                self.close_position(f"Trailing Stop (+{price_from_min:.1f}%)", current_rsi, current_price, market_data)
                return
            
            # 4. Salida por cambio de régimen de mercado
            elif (market_regime == 'volatile' and volatility > 4.0 and 
                  self.position.get('entry_market_regime') != 'volatile'):
                self.close_position("Mercado muy volátil", current_rsi, current_price, market_data)
                return
            
            # 5. Cambio de tendencia a alcista
            elif trend_direction == 'bullish':
                if current_rsi < 30 or current_price > ema_fast:
                    self.close_position("Tendencia alcista + señales adversas", current_rsi, current_price, market_data)
                    return
                else:
                    self.logger.warning("⚠️ Tendencia alcista detectada pero manteniendo posición (sin señales adversas)")
            
            # 6. RSI extremadamente oversold + precio sobre EMA21
            elif current_rsi < 20 and current_price > ema_fast:
                self.close_position("RSI extremo + ruptura EMA21", current_rsi, current_price, market_data)
                return
    
    def log_trade(self, action, side=None, price=None, quantity=None, rsi=None, 
                  ema_fast=None, ema_slow=None, ema_trend=None, trend_direction=None,
                  reason=None, pnl_pct=None, duration_hours=None, confirmation_time=None,
                  confidence=None, market_regime=None, volatility=None):
        """Registra trades con datos optimizados"""
        timestamp = datetime.now()
        balance = self.get_account_balance()
        
        try:
            with open(self.trades_csv, 'a', newline='') as f:
                writer = csv.writer(f)
                
                if action == 'OPEN':
                    volume_confirmed = "YES" if hasattr(self, '_last_volume_confirmation') and self._last_volume_confirmation else "NO"
                    
                    writer.writerow([
                        timestamp.isoformat(), action, side, price, quantity, rsi,
                        ema_fast or 0, ema_slow or 0, ema_trend or 0, trend_direction or '',
                        self.position['stop_loss'] if self.position else '',
                        self.position['take_profit'] if self.position else '',
                        reason or '', '', '', balance, '', '',
                        "YES" if confirmation_time else "NO",
                        confirmation_time or 0, 'optimized_entry',
                        confidence or 0, market_regime or '', volatility or 0, volume_confirmed
                    ])
                else:  # CLOSE
                    pnl_usdt = (pnl_pct / 100) * balance if pnl_pct else 0
                    writer.writerow([
                        timestamp.isoformat(), action, side, price, quantity, rsi,
                        ema_fast or 0, ema_slow or 0, ema_trend or 0, trend_direction or '',
                        '', '', reason or '', pnl_pct or 0, pnl_usdt,
                        '', balance, duration_hours or 0, '', '', '',
                        confidence or 0, market_regime or '', volatility or 0, ''
                    ])
        except Exception as e:
            self.logger.error(f"Error guardando trade: {e}")
        
        # Actualizar métricas
        if action == 'CLOSE' and pnl_pct is not None:
            self.update_performance_metrics(pnl_pct)
    
    def update_performance_metrics(self, pnl_pct):
        """Actualiza métricas de rendimiento"""
        self.performance_metrics['total_trades'] += 1
        self.performance_metrics['total_pnl'] += pnl_pct
        
        if pnl_pct > 0:
            self.performance_metrics['winning_trades'] += 1
            self.performance_metrics['consecutive_losses'] = 0
        else:
            self.performance_metrics['losing_trades'] += 1
            self.performance_metrics['consecutive_losses'] += 1
            
        if self.performance_metrics['consecutive_losses'] > self.performance_metrics['max_consecutive_losses']:
            self.performance_metrics['max_consecutive_losses'] = self.performance_metrics['consecutive_losses']
    
    def analyze_and_trade_optimized(self):
        """Análisis principal optimizado y ejecución de trades"""
        # Obtener datos del mercado
        market_data = self.get_market_data()
        if not market_data:
            return
            
        current_rsi = market_data['rsi']
        current_price = market_data['price']
        ema_fast = market_data['ema_fast']
        ema_slow = market_data['ema_slow']
        ema_trend = market_data['ema_trend']
        trend_direction = market_data['trend_direction']
        market_regime = market_data['market_regime']
        volatility = market_data['volatility']
        
        # Calcular separación de EMAs
        ema_separation = abs((ema_fast - ema_slow) / ema_slow) * 100 if ema_slow > 0 else 0
        
        # Log información del mercado con más detalles
        if self.in_position and self.position:
            pnl_pct = 0
            if self.position['side'] == 'long':
                pnl_pct = ((current_price - self.position['entry_price']) / self.position['entry_price']) * 100
                max_price = self.position.get('highest_price', current_price)
                trailing_stop = self.position.get('trailing_stop', 0)
                
                self.logger.info(f"📈 BTC: ${current_price:,.2f} | RSI: {current_rsi:.1f} | {trend_direction.upper()} | {market_regime.upper()}")
                self.logger.info(f"💰 PnL: {pnl_pct:+.2f}% | Max: ${max_price:.2f} | TS: ${trailing_stop:.2f} | Vol: {volatility:.1f}%")
                self.logger.info(f"📊 EMA21: ${ema_fast:.2f} | EMA50: ${ema_slow:.2f} | EMA200: ${ema_trend:.2f} | Sep: {ema_separation:.2f}%")
                
                # Mostrar información adicional de la posición
                entry_confidence = self.position.get('entry_confidence', 0)
                duration_hours = (datetime.now() - self.position['entry_time']).total_seconds() / 3600
                self.logger.info(f"🎯 Confianza entrada: {entry_confidence:.2f} | Duración: {duration_hours:.1f}h | Breakeven: {'✅' if self.position.get('breakeven_moved') else '❌'}")
                
            else:  # SHORT
                pnl_pct = ((self.position['entry_price'] - current_price) / self.position['entry_price']) * 100
                min_price = self.position.get('lowest_price', current_price)
                trailing_stop = self.position.get('trailing_stop', 0)
                
                self.logger.info(f"📉 BTC: ${current_price:,.2f} | RSI: {current_rsi:.1f} | {trend_direction.upper()} | {market_regime.upper()}")
                self.logger.info(f"💰 PnL: {pnl_pct:+.2f}% | Min: ${min_price:.2f} | TS: ${trailing_stop:.2f} | Vol: {volatility:.1f}%")
                self.logger.info(f"📊 EMA21: ${ema_fast:.2f} | EMA50: ${ema_slow:.2f} | EMA200: ${ema_trend:.2f} | Sep: {ema_separation:.2f}%")
                
                entry_confidence = self.position.get('entry_confidence', 0)
                duration_hours = (datetime.now() - self.position['entry_time']).total_seconds() / 3600
                self.logger.info(f"🎯 Confianza entrada: {entry_confidence:.2f} | Duración: {duration_hours:.1f}h | Breakeven: {'✅' if self.position.get('breakeven_moved') else '❌'}")
                
        else:
            # Sin posición - mostrar estado del mercado
            ema_order = "📈" if ema_fast > ema_slow > ema_trend else "📉" if ema_fast < ema_slow < ema_trend else "🔄"
            volume_status = "🔊" if market_data['volume'] > market_data['avg_volume'] * 1.2 else "🔇"
            
            self.logger.info(f"{ema_order} BTC: ${current_price:,.2f} | RSI: {current_rsi:.1f} | {trend_direction.upper()} | {market_regime.upper()} {volume_status}")
            self.logger.info(f"📊 EMA21: ${ema_fast:.2f} | EMA50: ${ema_slow:.2f} | EMA200: ${ema_trend:.2f} | Sep: {ema_separation:.2f}% | Vol: {volatility:.1f}%")
            
            # Mostrar umbrales dinámicos
            oversold, overbought, _, _ = self.get_dynamic_rsi_thresholds(trend_direction, ema_separation, market_regime)
            consecutive_losses = self.performance_metrics['consecutive_losses']
            self.logger.info(f"🎯 RSI Dinámico: OS≤{oversold:.0f} | OB≥{overbought:.0f} | Pérdidas consecutivas: {consecutive_losses}")
        
        # Verificar condiciones de salida si estamos en posición
        self.check_exit_conditions_optimized(current_price, current_rsi, market_data)
        
        # Si estamos en posición, no buscar nuevas señales
        if self.in_position:
            return
        
        # Verificar confirmación de señales pendientes
        confirmed, signal_type = self.check_enhanced_swing_confirmation(market_data)
        
        if confirmed:
            current_time = time.time()
            
            # Calcular tiempo de confirmación
            confirmation_time_hours = 0
            if self.signal_trigger_time:
                confirmation_time_hours = (datetime.now() - self.signal_trigger_time).total_seconds() / 3600
            
            if signal_type == 'long':
                if self.open_long_position(market_data, confirmation_time_hours):
                    self.last_signal_time = current_time
            elif signal_type == 'short':
                if self.open_short_position(market_data, confirmation_time_hours):
                    self.last_signal_time = current_time
        
        # Solo buscar nuevas señales si no hay señales pendientes y ha pasado tiempo suficiente
        elif not (self.pending_long_signal or self.pending_short_signal):
            current_time = time.time()
            if current_time - self.last_signal_time >= self.min_time_between_signals:
                self.detect_enhanced_swing_signal(market_data)
    
    def run(self):
        """Ejecuta el bot optimizado en un loop continuo"""
        self.logger.info("🚀 Optimized RSI + EMA + Trend Filter Bot v3.0 iniciado")
        self.logger.info(f"📊 Timeframe: {self.timeframe} | RSI({self.rsi_period}) | Dinámico: OS/OB adaptativo")
        self.logger.info(f"📈 EMAs: Fast({self.ema_fast_period}) | Slow({self.ema_slow_period}) | Trend({self.ema_trend_period})")
        self.logger.info(f"⚡ Leverage: {self.leverage}x | Risk: {self.base_position_size_pct}% (dinámico) | SL: {self.stop_loss_pct}% | TP: {self.take_profit_pct}%")
        self.logger.info(f"🎯 Swing Confirmación: {self.swing_confirmation_threshold}% | Max espera: {self.max_swing_wait} períodos")
        self.logger.info(f"🛡️ Trailing Stop: {self.trailing_stop_distance}% (dinámico) | Breakeven: {self.breakeven_threshold}%")
        self.logger.info(f"🧠 Confianza mínima: {self.confidence_threshold:.0%} | Max pérdidas consecutivas: {self.max_consecutive_losses}")
        self.logger.info(f"🔊 Volumen: {self.volume_confirmation_threshold:.0%} sobre promedio | Timeframe superior: Activado")
        self.logger.info(f"💾 Estado guardado en: {self.state_file}")
        self.logger.info(f"🐳 Ejecutándose en Docker - PID: {os.getpid()}")
        
        # Para swing trading optimizado, verificar cada 20 minutos
        check_interval = 1200  # 20 minutos en segundos
        iteration = 0
        
        try:
            while True:
                self.analyze_and_trade_optimized()
                
                # Mostrar resumen cada 3 horas (9 iteraciones de 20 min)
                iteration += 1
                if iteration % 9 == 0:
                    self.log_performance_summary()
                
                # Guardar estado cada hora (3 iteraciones)
                if iteration % 3 == 0:
                    self.save_bot_state()
                
                time.sleep(check_interval)
                
        except KeyboardInterrupt:
            self.logger.info("🛑 Bot detenido por el usuario (KeyboardInterrupt)")
            if self.in_position:
                self.close_position("Bot detenido")
            self.save_bot_state()
            self.log_performance_summary()
                
        except Exception as e:
            self.logger.error(f"❌ Error en el bot: {e}")
            if self.in_position:
                self.close_position("Error del bot")
            self.save_bot_state()
            raise
    
    def log_performance_summary(self):
        """Muestra resumen de performance optimizado"""
        metrics = self.performance_metrics
        
        self.logger.info("="*80)
        self.logger.info("📊 RESUMEN DE PERFORMANCE BOT OPTIMIZADO v3.0")
        self.logger.info("="*80)
        
        # Estadísticas de señales y filtros mejoradas
        signal_confirmation_rate = 0
        if metrics['signals_detected'] > 0:
            signal_confirmation_rate = (metrics['signals_confirmed'] / metrics['signals_detected']) * 100
        
        self.logger.info(f"🔔 Señales detectadas: {metrics['signals_detected']}")
        self.logger.info(f"✅ Señales confirmadas: {metrics['signals_confirmed']}")
        self.logger.info(f"⏰ Señales expiradas: {metrics['signals_expired']}")
        self.logger.info(f"🔍 Señales baja confianza: {metrics['signals_low_confidence']}")
        self.logger.info(f"📈 Tasa de confirmación: {signal_confirmation_rate:.1f}%")
        self.logger.info(f"🎯 Filtros de tendencia: {metrics['trend_filters_applied']}")
        self.logger.info(f"📊 Confirmaciones EMA: {metrics['ema_confirmations']}")
        self.logger.info(f"🔊 Confirmaciones volumen: {metrics['volume_confirmations']}")
        self.logger.info(f"🔄 Entradas por pullback: {metrics['pullback_entries']}")
        self.logger.info(f"🔧 Recuperaciones: {metrics['recoveries_performed']}")
        self.logger.info(f"⚙️ Ajustes adaptativos: {metrics['adaptive_adjustments']}")
        self.logger.info(f"🔄 Cambios de régimen: {metrics['regime_changes']}")
        self.logger.info("-" * 60)
        
        # Estadísticas de trading
        if metrics['total_trades'] == 0:
            self.logger.info("📊 Sin trades completados aún")
        else:
            win_rate = (metrics['winning_trades'] / metrics['total_trades']) * 100
            avg_pnl = metrics['total_pnl'] / metrics['total_trades']
            
            self.logger.info(f"🔢 Total Trades: {metrics['total_trades']}")
            self.logger.info(f"🎯 Win Rate: {win_rate:.1f}%")
            self.logger.info(f"💰 PnL Total: {metrics['total_pnl']:+.2f}%")
            self.logger.info(f"✅ Ganadores: {metrics['winning_trades']}")
            self.logger.info(f"❌ Perdedores: {metrics['losing_trades']}")
            self.logger.info(f"📉 Pérdidas consecutivas actuales: {metrics['consecutive_losses']}")
            self.logger.info(f"📉 Max pérdidas consecutivas: {metrics['max_consecutive_losses']}")
            
            # Calcular métricas avanzadas
            if metrics['winning_trades'] > 0 and metrics['losing_trades'] > 0:
                winning_trades = [t for t in self.trades_log if t.get('pnl_pct', 0) > 0]
                losing_trades = [t for t in self.trades_log if t.get('pnl_pct', 0) < 0]
                
                if winning_trades and losing_trades:
                    avg_win = sum([t.get('pnl_pct', 0) for t in winning_trades]) / len(winning_trades)
                    avg_loss = sum([t.get('pnl_pct', 0) for t in losing_trades]) / len(losing_trades)
                    profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0
                    
                    self.logger.info(f"📈 Ganancia promedio: {avg_win:+.2f}%")
                    self.logger.info(f"📉 Pérdida promedio: {avg_loss:+.2f}%")
                    self.logger.info(f"⚖️ Factor de Ganancia: {profit_factor:.2f}")
        
        self.logger.info(f"💵 Balance Actual: ${self.get_account_balance():.2f}")
        
        # Estado actual con información optimizada
        if self.in_position:
            pos_type = "RECUPERADA" if self.position.get('recovered') else "ACTIVA"
            duration = (datetime.now() - self.position['entry_time']).total_seconds() / 3600
            confidence = self.position.get('entry_confidence', 0)
            regime = self.position.get('entry_market_regime', 'unknown')
            
            self.logger.info(f"📍 Posición {pos_type}: {self.position['side'].upper()} ({duration:.1f}h)")
            self.logger.info(f"🎯 Confianza entrada: {confidence:.2f} | Régimen entrada: {regime}")
            self.logger.info(f"🛡️ Breakeven movido: {'SÍ' if self.position.get('breakeven_moved') else 'NO'}")
            
        elif self.pending_long_signal:
            confidence = self.signal_confidence
            remaining = self.max_swing_wait - self.swing_wait_count
            self.logger.info(f"⏳ Esperando confirmación SWING LONG ({self.swing_wait_count}/{self.max_swing_wait})")
            self.logger.info(f"🎯 Confianza señal: {confidence:.2f} | Períodos restantes: {remaining}")
            
        elif self.pending_short_signal:
            confidence = self.signal_confidence
            remaining = self.max_swing_wait - self.swing_wait_count
            self.logger.info(f"⏳ Esperando confirmación SWING SHORT ({self.swing_wait_count}/{self.max_swing_wait})")
            self.logger.info(f"🎯 Confianza señal: {confidence:.2f} | Períodos restantes: {remaining}")
            
        else:
            consecutive_losses = metrics['consecutive_losses']
            status = "PAUSADO" if consecutive_losses >= self.max_consecutive_losses else "ACTIVO"
            self.logger.info(f"🔍 Buscando oportunidades... | Estado: {status}")
            self.logger.info(f"📊 Tendencia: {self.trend_direction} | Régimen: {self.market_regime} | Volatilidad: {self.current_volatility:.1f}%")
        
        # Información de EMAs y mercado actuales
        if hasattr(self, 'last_ema_fast') and self.last_ema_fast > 0:
            ema_alignment = "ALCISTA" if self.last_ema_fast > self.last_ema_slow > self.last_ema_trend else \
                           "BAJISTA" if self.last_ema_fast < self.last_ema_slow < self.last_ema_trend else "NEUTRAL"
            
            self.logger.info(f"📊 Alineación EMAs: {ema_alignment}")
            self.logger.info(f"📈 EMA21: ${self.last_ema_fast:.2f} | EMA50: ${self.last_ema_slow:.2f} | EMA200: ${self.last_ema_trend:.2f}")
            
            # Separación entre EMAs y umbrales dinámicos
            if self.last_ema_slow > 0:
                ema_separation = abs((self.last_ema_fast - self.last_ema_slow) / self.last_ema_slow) * 100
                self.logger.info(f"📏 Separación EMA21-EMA50: {ema_separation:.2f}%")
                
                # Mostrar umbrales RSI dinámicos actuales
                oversold, overbought, _, _ = self.get_dynamic_rsi_thresholds(
                    self.trend_direction, ema_separation, self.market_regime
                )
                self.logger.info(f"🎯 RSI Dinámico actual: Oversold≤{oversold:.0f} | Overbought≥{overbought:.0f}")
        
        # Estadísticas de volumen y timeframes
        if hasattr(self, 'avg_volume') and self.avg_volume > 0:
            current_vol_ratio = (self.avg_volume / 1000000) if self.avg_volume > 1000000 else self.avg_volume
            vol_status = 'Alto' if current_vol_ratio > 1.2 else 'Normal' if current_vol_ratio > 0.8 else 'Bajo'
            self.logger.info(f"🔊 Volumen promedio: {self.avg_volume:,.0f} | Estado volumen: {vol_status}")
        
        self.logger.info("="*80)


# Ejemplo de uso optimizado para swing trading
if __name__ == "__main__":
    
    print("🚀 Optimized RSI + EMA + Trend Filter Swing Bot v3.0 - Docker Edition")
    print(f"🐳 Python PID: {os.getpid()}")
    print(f"🐳 Working Directory: {os.getcwd()}")
    
    # Configuración con variables de entorno
    API_KEY = os.getenv('BINANCE_API_KEY')
    API_SECRET = os.getenv('BINANCE_API_SECRET')
    USE_TESTNET = os.getenv('USE_TESTNET', 'true').lower() == 'true'
    
    if not API_KEY or not API_SECRET:
        print("❌ ERROR: Variables de entorno no configuradas")
        print("🐳 En Docker, asegúrate de que el .env esté configurado correctamente")
        print("🐳 Variables requeridas: BINANCE_API_KEY, BINANCE_API_SECRET")
        exit(1)
    
    print(f"🤖 Iniciando bot optimizado en modo: {'TESTNET' if USE_TESTNET else 'REAL TRADING'}")
    print("🔔 CARACTERÍSTICAS OPTIMIZADAS v3.0:")
    print("  • RSI con umbrales dinámicos adaptativos")
    print("  • Confirmación de volumen y timeframe superior")
    print("  • Sistema de confianza para filtrar señales")
    print("  • Tamaño de posición dinámico basado en confianza")
    print("  • Trailing stop adaptativo a volatilidad")
    print("  • Detección de régimen de mercado")
    print("  • Protección contra pérdidas consecutivas")
    print("  • Recuperación automática de estado")
    print("🐳 DOCKER: Auto-restart + persistencia garantizada")
    
    if not USE_TESTNET:
        print("⚠️  ADVERTENCIA: Vas a usar DINERO REAL")
        print("🐳 En modo Docker, no se solicita confirmación manual")
        print("🐳 Para cancelar, detén el contenedor: docker-compose down")
    
    try:
        print("🚀 Creando instancia del bot optimizado...")
        bot = OptimizedBinanceRSIEMABot(
            api_key=API_KEY,
            api_secret=API_SECRET, 
            testnet=USE_TESTNET
        )
        
        print("✅ Bot optimizado inicializado correctamente")
        print("🔄 Iniciando loop principal optimizado...")
        bot.run()
        
    except KeyboardInterrupt:
        print("🛑 Bot detenido por señal de usuario")
        
    except Exception as e:
        print(f"❌ Error crítico: {e}")
        print("🐳 Docker reiniciará automáticamente el contenedor")
        exit(1)import ccxt
import pandas as pd
import numpy as np
import time
import logging
import signal
from datetime import datetime
import json
import csv
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

class OptimizedBinanceRSIEMABot:
    def __init__(self, api_key, api_secret, testnet=True):
        """
        Bot de trading RSI + EMA + Filtro de Tendencia Optimizado - v3.0
        
        Args:
            api_key: Tu API key de Binance
            api_secret: Tu API secret de Binance  
            testnet: True para usar testnet, False para trading real
        """
        
        # IMPORTANTE: Configurar logging PRIMERO
        self.setup_logging()
        
        # Configurar variables básicas ANTES de exchange
        self.testnet = testnet
        self.symbol = 'BTC/USDT'
        self.timeframe = '4h'  # Timeframe para swing trading
        
        # Configuración RSI OPTIMIZADA
        self.rsi_period = 14
        self.base_rsi_oversold = 30
        self.base_rsi_overbought = 70
        
        # Configuración EMA
        self.ema_fast_period = 21
        self.ema_slow_period = 50
        self.ema_trend_period = 200  # EMA para filtro de tendencia principal
        
        # Gestión de riesgo mejorada
        self.leverage = 1
        self.base_position_size_pct = 3  # Base para cálculo dinámico
        self.stop_loss_pct = 3  
        self.take_profit_pct = 6  
        self.min_balance_usdt = 50
        self.min_notional_usdt = 12
        
        # NUEVAS VARIABLES PARA ESTRATEGIA OPTIMIZADA
        self.ema_separation_min = 0.2  # Mínima separación % entre EMAs
        self.trend_confirmation_candles = 2  
        self.flexible_pullback = True  # Pullback más flexible
        
        # VARIABLES PARA CONFIRMACIÓN DE SWING OPTIMIZADA
        self.swing_confirmation_threshold = 0.3  # Reducido de 0.5% a 0.3%
        self.max_swing_wait = 6  # Aumentado de 4 a 6 períodos
        self.min_time_between_signals = 7200  # Reducido a 2 horas
        
        # VARIABLES PARA TRAILING STOP INTELIGENTE
        self.trailing_stop_distance = 2.5  
        self.breakeven_threshold = 1.5  
        
        # NUEVAS VARIABLES PARA OPTIMIZACIÓN
        self.volume_confirmation_threshold = 1.2  # 20% sobre promedio
        self.confidence_threshold = 0.65  # Umbral de confianza para señales
        self.max_consecutive_losses = 3  # Parar después de 3 pérdidas seguidas
        self.adaptive_mode = True  # Modo adaptativo para parámetros
        
        # ARCHIVOS DE PERSISTENCIA (compatible con Docker)
        self.logs_dir = os.path.join(os.getcwd(), 'logs')
        self.data_dir = os.path.join(os.getcwd(), 'data')
        
        # Crear directorios si no existen
        os.makedirs(self.logs_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
        
        self.state_file = os.path.join(self.data_dir, f'bot_state_{datetime.now().strftime("%Y%m%d")}.json')
        self.recovery_file = os.path.join(self.logs_dir, f'recovery_log_{datetime.now().strftime("%Y%m%d")}.txt')
        
        # Estado del bot
        self.position = None
        self.in_position = False
        self.last_signal_time = 0
        
        # NUEVOS ESTADOS PARA ESTRATEGIA OPTIMIZADA
        self.pending_long_signal = False
        self.pending_short_signal = False
        self.signal_trigger_price = None
        self.signal_trigger_time = None
        self.signal_confidence = 0
        self.swing_wait_count = 0
        self.last_rsi = 50
        self.last_price = 0
        self.last_ema_fast = 0
        self.last_ema_slow = 0
        self.last_ema_trend = 0
        self.trend_direction = 'neutral'  
        self.market_regime = 'trending'  # 'trending', 'ranging', 'volatile'
        self.avg_volume = 0
        self.current_volatility = 0
        
        # Historial de datos para análisis
        self.price_history = []
        self.volume_history = []
        self.ema_history = {'fast': [], 'slow': [], 'trend': []}
        
        # Métricas para análisis AMPLIADAS
        self.trades_log = []
        self.market_data_log = []
        self.performance_metrics = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0,
            'max_drawdown': 0,
            'consecutive_losses': 0,
            'max_consecutive_losses': 0,
            'signals_detected': 0,
            'signals_confirmed': 0,
            'signals_expired': 0,
            'signals_low_confidence': 0,
            'recoveries_performed': 0,
            'trend_filters_applied': 0,
            'ema_confirmations': 0,
            'pullback_entries': 0,
            'volume_confirmations': 0,
            'adaptive_adjustments': 0,
            'regime_changes': 0
        }
        
        # Configuración del exchange DESPUÉS de definir variables
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'sandbox': testnet,
            'enableRateLimit': True,
            'options': {
                'adjustForTimeDifference': True,
            }
        })
        
        # Verificar conexión después de configurar todo
        self.verify_connection()
        
        # Inicializar archivos de logs al final
        self.init_log_files()
        
        # Recuperar estado y posiciones al iniciar
        self.recover_bot_state()
        
    def setup_logging(self):
        """Configura sistema de logging (compatible con Docker)"""
        logs_dir = os.path.join(os.getcwd(), 'logs')
        os.makedirs(logs_dir, exist_ok=True)
            
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        log_file = os.path.join(logs_dir, f'optimized_bot_{datetime.now().strftime("%Y%m%d")}.log')
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        self.logger.info(f"🚀 Optimized RSI+EMA Bot v3.0 iniciando - Logs en: {log_file}")
        
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """Maneja señales de Docker (SIGTERM, SIGINT)"""
        signal_names = {2: 'SIGINT', 15: 'SIGTERM'}
        signal_name = signal_names.get(signum, f'Signal {signum}')
        
        self.logger.info(f"🐳 Recibida señal {signal_name} - Cerrando bot gracefully...")
        
        if self.in_position:
            self.logger.info("💾 Cerrando posición antes de salir...")
            self.close_position("Señal Docker")
        
        self.save_bot_state()
        self.log_performance_summary()
        
        self.logger.info("🐳 Bot cerrado correctamente")
        exit(0)
        
    def verify_connection(self):
        """Verifica la conexión con Binance"""
        try:
            self.exchange.load_markets()
            
            if self.symbol not in self.exchange.markets:
                available_symbols = [s for s in self.exchange.markets.keys() if 'BTC' in s and 'USDT' in s]
                self.logger.warning(f"Símbolo {self.symbol} no encontrado. Disponibles: {available_symbols[:5]}")
                
            balance = self.exchange.fetch_balance()
            self.logger.info(f"✅ Conexión exitosa con Binance {'Testnet' if self.testnet else 'Mainnet'}")
            
            usdt_balance = balance.get('USDT', {}).get('free', 0)
            self.logger.info(f"💰 Balance USDT disponible: ${usdt_balance:.2f}")
            
        except Exception as e:
            self.logger.error(f"❌ Error de conexión: {e}")
            raise
    
    def calculate_ema(self, prices, period):
        """Calcula EMA (Exponential Moving Average)"""
        try:
            if isinstance(prices, (list, np.ndarray)):
                prices = pd.Series(prices)
            
            return prices.ewm(span=period, adjust=False).mean().iloc[-1]
            
        except Exception as e:
            self.logger.error(f"Error calculando EMA: {e}")
            return 0
    
    def calculate_rsi(self, prices, period=14):
        """Calcula el RSI"""
        try:
            if isinstance(prices, (list, np.ndarray)):
                prices = pd.Series(prices)
            
            delta = prices.diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            
            avg_gain = gain.rolling(window=period).mean()
            avg_loss = loss.rolling(window=period).mean()
            
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
            
        except Exception as e:
            self.logger.error(f"Error calculando RSI: {e}")
            return 50
    
    def calculate_volatility(self, prices, period=20):
        """Calcula volatilidad basada en desviación estándar de retornos"""
        try:
            if isinstance(prices, (list, np.ndarray)):
                prices = pd.Series(prices)
            
            returns = prices.pct_change().dropna()
            volatility = returns.rolling(window=period).std().iloc[-1]
            return volatility * 100 if not pd.isna(volatility) else 1.0
            
        except Exception as e:
            self.logger.error(f"Error calculando volatilidad: {e}")
            return 1.0
    
    def get_market_data(self):
        """Obtiene datos del mercado para calcular RSI y EMAs"""
        try:
            # Obtener más datos para EMAs y análisis
            limit = max(self.ema_trend_period + 50, 120)
            ohlcv = self.exchange.fetch_ohlcv(
                self.symbol, 
                self.timeframe, 
                limit=limit
            )
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Calcular indicadores básicos
            current_price = float(df['close'].iloc[-1])
            current_volume = float(df['volume'].iloc[-1])
            current_rsi = self.calculate_rsi(df['close'])
            current_volatility = self.calculate_volatility(df['close'])
            
            # Calcular EMAs
            ema_fast = self.calculate_ema(df['close'], self.ema_fast_period)
            ema_slow = self.calculate_ema(df['close'], self.ema_slow_period)
            ema_trend = self.calculate_ema(df['close'], self.ema_trend_period)
            
            # Calcular volumen promedio
            avg_volume = df['volume'].tail(20).mean()
            
            # Determinar dirección de tendencia y régimen de mercado
            trend_direction = self.determine_trend_direction(current_price, ema_fast, ema_slow, ema_trend)
            market_regime = self.detect_market_regime(df, current_volatility)
            
            # Obtener confirmación de timeframe superior
            htf_bias = self.get_higher_timeframe_bias()
            
            # Log datos de mercado
            self.log_market_data(current_price, current_rsi, current_volume, ema_fast, ema_slow, 
                               ema_trend, trend_direction, current_volatility, market_regime)
            
            return {
                'price': current_price,
                'rsi': current_rsi,
                'volume': current_volume,
                'avg_volume': avg_volume,
                'volatility': current_volatility,
                'ema_fast': ema_fast,
                'ema_slow': ema_slow,
                'ema_trend': ema_trend,
                'trend_direction': trend_direction,
                'market_regime': market_regime,
                'htf_bias': htf_bias,
                'dataframe': df
            }
            
        except Exception as e:
            self.logger.error(f"Error obteniendo datos del mercado: {e}")
            return None
    
    def determine_trend_direction(self, price, ema_fast, ema_slow, ema_trend):
        """Determina la dirección de la tendencia basada en EMAs"""
        # Tendencia alcista: EMA21 > EMA50 > EMA200 y precio > EMA200
        if ema_fast > ema_slow and ema_slow > ema_trend and price > ema_trend:
            # Verificar separación mínima entre EMAs
            fast_slow_sep = ((ema_fast - ema_slow) / ema_slow) * 100
            if fast_slow_sep >= self.ema_separation_min:
                return 'bullish'
        
        # Tendencia bajista: EMA21 < EMA50 < EMA200 y precio < EMA200
        elif ema_fast < ema_slow and ema_slow < ema_trend and price < ema_trend:
            # Verificar separación mínima entre EMAs
            slow_fast_sep = ((ema_slow - ema_fast) / ema_fast) * 100
            if slow_fast_sep >= self.ema_separation_min:
                return 'bearish'
        
        return 'neutral'
    
    def detect_market_regime(self, df, volatility):
        """Detecta el régimen del mercado: trending, ranging, volatile"""
        try:
            # Calcular ADX simplificado para detectar tendencia
            recent_prices = df['close'].tail(20)
            price_range = recent_prices.max() - recent_prices.min()
            price_change = abs(recent_prices.iloc[-1] - recent_prices.iloc[0])
            
            # Ratio de cambio vs rango
            trend_ratio = price_change / price_range if price_range > 0 else 0
            
            # Clasificar régimen
            if volatility > 3.0:  # Alta volatilidad
                return 'volatile'
            elif trend_ratio > 0.6:  # Fuerte tendencia
                return 'trending'
            else:  # Mercado lateral
                return 'ranging'
                
        except Exception as e:
            self.logger.error(f"Error detectando régimen de mercado: {e}")
            return 'trending'  # Default
    
    def get_higher_timeframe_bias(self):
        """Obtiene el sesgo del timeframe superior (1D)"""
        try:
            daily_ohlcv = self.exchange.fetch_ohlcv(self.symbol, '1d', limit=50)
            daily_df = pd.DataFrame(daily_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            daily_ema21 = self.calculate_ema(daily_df['close'], 21)
            daily_ema50 = self.calculate_ema(daily_df['close'], 50)
            current_price = daily_df['close'].iloc[-1]
            
            if daily_ema21 > daily_ema50 and current_price > daily_ema21:
                return 'bullish_htf'
            elif daily_ema21 < daily_ema50 and current_price < daily_ema21:
                return 'bearish_htf'
            else:
                return 'neutral_htf'
        except Exception as e:
            self.logger.error(f"Error obteniendo bias HTF: {e}")
            return 'neutral_htf'
    
    def get_dynamic_rsi_thresholds(self, trend_direction, ema_separation, market_regime):
        """Calcula umbrales RSI dinámicos basados en condiciones de mercado"""
        
        # Umbrales base
        oversold = self.base_rsi_oversold
        overbought = self.base_rsi_overbought
        
        # Ajustes por tendencia
        if trend_direction == 'bullish':
            # En mercados alcistas, RSI raramente baja de 40
            oversold = 40 if ema_separation > 1.0 else 35
            neutral_low = 45
            neutral_high = 65
        elif trend_direction == 'bearish':
            # En mercados bajistas, RSI raramente sube de 60
            overbought = 60 if ema_separation > 1.0 else 65
            neutral_low = 35
            neutral_high = 55
        else:
            # Mercado neutral - usar valores originales
            neutral_low = 40
            neutral_high = 60
        
        # Ajustes por régimen de mercado
        if market_regime == 'ranging':
            # En mercados laterales, usar umbrales más extremos
            oversold = max(oversold - 5, 25)
            overbought = min(overbought + 5, 75)
        elif market_regime == 'volatile':
            # En mercados volátiles, ser más conservador
            oversold = min(oversold + 5, 45)
            overbought = max(overbought - 5, 55)
        
        return oversold, overbought, neutral_low, neutral_high
    
    def calculate_signal_confidence(self, rsi, volume_confirmation, ema_separation, 
                                  trend_direction, htf_bias, price_pattern_score=0):
        """Calcula puntuación de confianza para señales (0-1)"""
        confidence = 0.5  # Confianza base
        
        # Alineación RSI con tendencia
        if trend_direction == 'bullish' and 35 <= rsi <= 50:
            confidence += 0.2
        elif trend_direction == 'bearish' and 50 <= rsi <= 65:
            confidence += 0.2
        elif trend_direction == 'neutral' and (rsi <= 35 or rsi >= 65):
            confidence += 0.15
        
        # Confirmación de volumen
        if volume_confirmation:
            confidence += 0.15
        
        # Separación de EMAs (tendencia más fuerte = mayor confianza)
        if ema_separation > 1.5:
            confidence += 0.2
        elif ema_separation > 0.8:
            confidence += 0.1
        
        # Alineación con timeframe superior
        if (trend_direction == 'bullish' and htf_bias == 'bullish_htf') or \
           (trend_direction == 'bearish' and htf_bias == 'bearish_htf'):
            confidence += 0.15
        
        # Patrones de precio
        confidence += price_pattern_score
        
        return min(confidence, 1.0)
    
    def is_near_ema_support(self, price, ema_fast, ema_slow):
        """Verifica si el precio está cerca de niveles de soporte EMA"""
        # Más flexible que la versión original
        distance_to_fast = abs((price - ema_fast) / ema_fast) * 100
        distance_to_slow = abs((price - ema_slow) / ema_slow) * 100
        
        # Precio dentro del 2% de EMA21 o 2.5% de EMA50
        if distance_to_fast <= 2.0:
            return True, 'EMA21'
        elif distance_to_slow <= 2.5:
            return True, 'EMA50'
        # Precio entre EMAs también es válido
        elif min(ema_slow, ema_fast) <= price <= max(ema_slow, ema_fast):
            return True, 'Entre_EMAs'
        
        return False, 'No_support'
    
    def is_near_ema_resistance(self, price, ema_fast, ema_slow):
        """Verifica si el precio está cerca de resistencia EMA para shorts"""
        distance_to_fast = abs((price - ema_fast) / ema_fast) * 100
        distance_to_slow = abs((price - ema_slow) / ema_slow) * 100
        
        # Precio dentro del 2% de EMA21 o 2.5% de EMA50 (desde arriba)
        if price > ema_fast and distance_to_fast <= 2.0:
            return True
        elif price > ema_slow and distance_to_slow <= 2.5:
            return True
        elif min(ema_slow, ema_fast) <= price <= max(ema_slow, ema_fast):
            return True
        
        return False
    
    def detect_price_patterns(self, df):
        """Detecta patrones de precio que pueden indicar reversal"""
        try:
            if len(df) < 5:
                return 0
            
            recent_candles = df.tail(5)
            last_candle = recent_candles.iloc[-1]
            
            # Calcular tamaños de cuerpo y mechas
            body_size = abs(last_candle['close'] - last_candle['open'])
            candle_range = last_candle['high'] - last_candle['low']
            lower_wick = min(last_candle['open'], last_candle['close']) - last_candle['low']
            
            pattern_score = 0
            
            # Patrón Hammer/Doji (reversal alcista)
            if candle_range > 0 and body_size / candle_range < 0.3 and lower_wick > body_size * 2:
                pattern_score += 0.15
                
            # Patrón de engulfing alcista
            if len(recent_candles) >= 2:
                prev_candle = recent_candles.iloc[-2]
                if (last_candle['close'] > last_candle['open'] and  # Vela verde
                    prev_candle['close'] < prev_candle['open'] and  # Vela roja anterior
                    last_candle['close'] > prev_candle['open'] and  # Engulfs el cuerpo
                    last_candle['open'] < prev_candle['close']):
                    pattern_score += 0.2
            
            return pattern_score
            
        except Exception as e:
            self.logger.error(f"Error detectando patrones: {e}")
            return 0
    
    def detect_enhanced_swing_signal(self, market_data):
        """Detección mejorada de señales con múltiples confirmaciones"""
        price = market_data['price']
        rsi = market_data['rsi']
        volume = market_data['volume']
        avg_volume = market_data['avg_volume']
        ema_fast = market_data['ema_fast']
        ema_slow = market_data['ema_slow']
        ema_trend = market_data['ema_trend']
        trend_direction = market_data['trend_direction']
        market_regime = market_data['market_regime']
        htf_bias = market_data['htf_bias']
        df = market_data['dataframe']
        
        # Solo buscar señales si no hay señales pendientes
        if self.pending_long_signal or self.pending_short_signal:
            return False
        
        # Parar si hay demasiadas pérdidas consecutivas
        if self.performance_metrics['consecutive_losses'] >= self.max_consecutive_losses:
            self.logger.warning(f"🛑 Máximo de pérdidas consecutivas alcanzado ({self.max_consecutive_losses})")
            return False
        
        # Calcular separación de EMAs
        ema_separation = abs((ema_fast - ema_slow) / ema_slow) * 100
        
        # Obtener umbrales dinámicos
        oversold, overbought, neutral_low, neutral_high = self.get_dynamic_rsi_thresholds(
            trend_direction, ema_separation, market_regime
        )
        
        # Confirmación de volumen
        volume_confirmation = volume > avg_volume * self.volume_confirmation_threshold
        
        # Detectar patrones de precio
        price_pattern_score = self.detect_price_patterns(df)
        
        # SEÑAL LONG MEJORADA
        if trend_direction == 'bullish' and not self.in_position:
            # Verificar RSI con umbrales dinámicos
            rsi_condition = rsi <= oversold or (rsi < 50 and rsi > oversold - 10)
            
            # Verificar soporte en EMAs
            near_support, support_type = self.is_near_ema_support(price, ema_fast, ema_slow)
            
            # Condiciones adicionales
            price_above_ema200 = price > ema_trend
            ascending_emas = ema_fast > ema_slow > ema_trend
            htf_aligned = htf_bias in ['bullish_htf', 'neutral_htf']
            
            if rsi_condition and price_above_ema200 and ascending_emas:
                # Calcular confianza
                confidence = self.calculate_signal_confidence(
                    rsi, volume_confirmation, ema_separation, 
                    trend_direction, htf_bias, price_pattern_score
                )
                
                # Si está cerca de soporte o tiene alta confianza, proceder
                if (near_support and confidence > 0.6) or confidence > self.confidence_threshold:
                    self.pending_long_signal = True
                    self.signal_trigger_price = price
                    self.signal_trigger_time = datetime.now()
                    self.signal_confidence = confidence
                    self.swing_wait_count = 0
                    
                    self.performance_metrics['signals_detected'] += 1
                    self.performance_metrics['trend_filters_applied'] += 1
                    if volume_confirmation:
                        self.performance_metrics['volume_confirmations'] += 1
                    if near_support:
                        self.performance_metrics['pullback_entries'] += 1
                    
                    self.logger.info(f"🟡 SEÑAL LONG MEJORADA - RSI: {rsi:.1f}({oversold:.0f}) | Confianza: {confidence:.2f}")
                    self.logger.info(f"📍 Precio: ${price:.2f} | Soporte: {support_type} | HTF: {htf_bias}")
                    volume_symbol = '+' if volume_confirmation else '-'
                    self.logger.info(f"🔊 Volumen: {volume_symbol} | Patrón: {price_pattern_score:.2f}")
                    self.logger.info(f"🎯 Régimen: {market_regime} | EMA Sep: {ema_separation:.2f}%")
                    
                    return True
        
        # SEÑAL SHORT MEJORADA  
        elif trend_direction == 'bearish' and not self.in_position:
            rsi_condition = rsi >= overbought or (rsi > 50 and rsi < overbought + 10)
            
            # Para shorts, verificar resistencia en EMAs
            near_resistance = self.is_near_ema_resistance(price, ema_fast, ema_slow)
            
            price_below_ema200 = price < ema_trend
            descending_emas = ema_fast < ema_slow < ema_trend
            htf_aligned = htf_bias in ['bearish_htf', 'neutral_htf']
            
            if rsi_condition and price_below_ema200 and descending_emas:
                confidence = self.calculate_signal_confidence(
                    rsi, volume_confirmation, ema_separation, 
                    trend_direction, htf_bias, price_pattern_score
                )
                
                if (near_resistance and confidence > 0.6) or confidence > self.confidence_threshold:
                    self.pending_short_signal = True
                    self.signal_trigger_price = price
                    self.signal_trigger_time = datetime.now()
                    self.signal_confidence = confidence
                    self.swing_wait_count = 0
                    
                    self.performance_metrics['signals_detected'] += 1
                    self.performance_metrics['trend_filters_applied'] += 1
                    if volume_confirmation:
                        self.performance_metrics['volume_confirmations'] += 1
                    
                    self.logger.info(f"🟡 SEÑAL SHORT MEJORADA - RSI: {rsi:.1f}({overbought:.0f}) | Confianza: {confidence:.2f}")
                    self.logger.info(f"📍 Precio: ${price:.2f} | HTF: {htf_bias}")
                    volume_symbol = '+' if volume_confirmation else '-'
                    self.logger.info(f"🔊 Volumen: {volume_symbol} | Patrón: {price_pattern_score:.2f}")
                    self.logger.info(f"🎯 Régimen: {market_regime} | EMA Sep: {ema_separation:.2f}%")
                    
                    return True
        
        return False
    
    def check_enhanced_swing_confirmation(self, market_data):
        """Verificación mejorada de confirmación de swing"""
        if not (self.pending_long_signal or self.pending_short_signal):
            return False, None
            
        current_price = market_data['price']
        current_rsi = market_data['rsi']
        trend_direction = market_data['trend_direction']
        volume_confirmation = market_data['volume'] > market_data['avg_volume'] * self.volume_confirmation_threshold
        
        self.swing_wait_count += 1
        
        # Verificar confirmación LONG
        if self.pending_long_signal:
            price_change_pct = ((current_price - self.signal_trigger_price) / self.signal_trigger_price) * 100
            
            # Condiciones para confirmar LONG (más flexibles)
            rsi_improved = current_rsi > 35  # RSI mejoró desde oversold
            price_moved_up = price_change_pct >= self.swing_confirmation_threshold
            trend_still_good = trend_direction in ['bullish', 'neutral']
            
            # Bonus por volumen o alta confianza inicial
            confidence_bonus = self.signal_confidence > 0.75
            volume_bonus = volume_confirmation
            
            if (price_moved_up and rsi_improved and trend_still_good) or \
               (price_change_pct >= self.swing_confirmation_threshold * 0.7 and (confidence_bonus or volume_bonus)):
                
                self.logger.info(f"✅ SWING LONG CONFIRMADO! Precio: +{price_change_pct:.2f}% | RSI: {current_rsi:.1f}")
                self.logger.info(f"📊 Confianza inicial: {self.signal_confidence:.2f} | Volumen: {'+' if volume_confirmation else '-'}")
                self.performance_metrics['signals_confirmed'] += 1
                self.performance_metrics['ema_confirmations'] += 1
                self.reset_signal_state()
                return True, 'long'
                
            elif self.swing_wait_count >= self.max_swing_wait:
                self.logger.warning(f"⏰ Señal LONG EXPIRADA - Sin confirmación en {self.max_swing_wait} períodos")
                self.performance_metrics['signals_expired'] += 1
                self.reset_signal_state()
                return False, None
                
            elif trend_direction == 'bearish':
                self.logger.warning("❌ Señal LONG CANCELADA - Tendencia cambió a bajista")
                self.performance_metrics['signals_expired'] += 1
                self.reset_signal_state()
                return False, None
        
        # Verificar confirmación SHORT
        elif self.pending_short_signal:
            price_change_pct = ((self.signal_trigger_price - current_price) / self.signal_trigger_price) * 100
            
            rsi_improved = current_rsi < 65
            price_moved_down = price_change_pct >= self.swing_confirmation_threshold
            trend_still_good = trend_direction in ['bearish', 'neutral']
            
            confidence_bonus = self.signal_confidence > 0.75
            volume_bonus = volume_confirmation
            
            if (price_moved_down and rsi_improved and trend_still_good) or \
               (price_change_pct >= self.swing_confirmation_threshold * 0.7 and (confidence_bonus or volume_bonus)):
                
                self.logger.info(f"✅ SWING SHORT CONFIRMADO! Precio: -{price_change_pct:.2f}% | RSI: {current_rsi:.1f}")
                self.logger.info(f"📊 Confianza inicial: {self.signal_confidence:.2f} | Volumen: {'+' if volume_confirmation else '-'}")
                self.performance_metrics['signals_confirmed'] += 1
                self.performance_metrics['ema_confirmations'] += 1
                self.reset_signal_state()
                return True, 'short'
                
            elif self.swing_wait_count >= self.max_swing_wait:
                self.logger.warning(f"⏰ Señal SHORT EXPIRADA - Sin confirmación en {self.max_swing_wait} períodos")
                self.performance_metrics['signals_expired'] += 1
                self.reset_signal_state()
                return False, None
                
            elif trend_direction == 'bullish':
                self.logger.warning("❌ Señal SHORT CANCELADA - Tendencia cambió a alcista")
                self.performance_metrics['signals_expired'] += 1
                self.reset_signal_state()
                return False, None
        
        # Log progreso de espera
        if self.swing_wait_count % 1 == 0:
            signal_type = "LONG" if self.pending_long_signal else "SHORT"
            remaining = self.max_swing_wait - self.swing_wait_count
            price_change = ((current_price - self.signal_trigger_price) / self.signal_trigger_price) * 100
            if self.pending_short_signal:
                price_change = -price_change
                
            self.logger.info(f"⏳ Esperando confirmación {signal_type}: {self.swing_wait_count}/{self.max_swing_wait} | "
                           f"Cambio: {price_change:+.2f}% | RSI: {current_rsi:.1f} | Confianza: {self.signal_confidence:.2f}")
        
        return False, None
    
    def reset_signal_state(self):
        """Resetea el estado de señales pendientes"""
        self.pending_long_signal = False
        self.pending_short_signal = False
        self.signal_trigger_price = None
        self.signal_trigger_time = None
        self.signal_confidence = 0
        self.swing_wait_count = 0
    
    def calculate_dynamic_position_size(self, price, confidence, volatility):
        """Calcula tamaño de posición dinámico basado en confianza y volatilidad"""
        balance = self.get_account_balance()
        
        if balance < self.min_balance_usdt:
            self.logger.warning(f"Balance insuficiente: ${balance:.2f} < ${self.min_balance_usdt}")
            return 0, 0
        
        # Tamaño base ajustado por confianza
        confidence_multiplier = 0.7 + (confidence * 0.6)  # Rango: 0.7 - 1.3
        
        # Ajuste por volatilidad (reducir en alta volatilidad)
        volatility_multiplier = max(0.6, 1 - (volatility * 0.1))
        
        # Ajuste por pérdidas consecutivas
        loss_multiplier = max(0.5, 1 - (self.performance_metrics['consecutive_losses'] * 0.15))
        
        # Calcular tamaño final
        adjusted_size_pct = self.base_position_size_pct * confidence_multiplier * volatility_multiplier * loss_multiplier
        position_value = balance * (adjusted_size_pct / 100)
        effective_position = position_value * self.leverage
        
        # Verificar mínimo notional
        if effective_position < self.min_notional_usdt:
            effective_position = self.min_notional_usdt
        
        quantity = round(effective_position / price, 6)
        final_notional = quantity * price
        
        self.logger.info(f"💰 Tamaño dinámico: {adjusted_size_pct:.1f}% | Confianza: {confidence:.2f} | Vol: {volatility:.1f}%")
        self.logger.info(f"📊 Multiplicadores - Conf: {confidence_multiplier:.2f} | Vol: {volatility_multiplier:.2f} | Loss: {loss_multiplier:.2f}")
        
        if final_notional < self.min_notional_usdt:
            self.logger.warning(f"Notional final insuficiente: ${final_notional:.2f}")
            return 0, 0
        
        return quantity, position_value
    
    def log_market_data(self, price, rsi, volume, ema_fast, ema_slow, ema_trend, 
                       trend_direction, volatility, market_regime, signal=None):
        """Registra datos de mercado con información ampliada"""
        timestamp = datetime.now()
        
        # Calcular PnL no realizado si estamos en posición
        unrealized_pnl = 0
        if self.in_position and self.position:
            if self.position['side'] == 'long':
                unrealized_pnl = ((price - self.position['entry_price']) / self.position['entry_price']) * 100 * self.leverage
            else:
                unrealized_pnl = ((self.position['entry_price'] - price) / self.position['entry_price']) * 100 * self.leverage
        
        # Estado de señal pendiente
        pending_signal = ""
        if self.pending_long_signal:
            pending_signal = f"LONG_WAIT_{self.swing_wait_count}/{self.max_swing_wait}_C{self.signal_confidence:.2f}"
        elif self.pending_short_signal:
            pending_signal = f"SHORT_WAIT_{self.swing_wait_count}/{self.max_swing_wait}_C{self.signal_confidence:.2f}"
        
        # Actualizar variables de estado
        self.last_rsi = rsi
        self.last_price = price
        self.last_ema_fast = ema_fast
        self.last_ema_slow = ema_slow
        self.last_ema_trend = ema_trend
        self.trend_direction = trend_direction
        self.current_volatility = volatility
        self.avg_volume = self.avg_volume * 0.9 + volume * 0.1 if self.avg_volume > 0 else volume
        
        # Detectar cambio de régimen
        if hasattr(self, 'market_regime') and self.market_regime != market_regime:
            self.performance_metrics['regime_changes'] += 1
            self.logger.info(f"🔄 Cambio de régimen: {self.market_regime} → {market_regime}")
        
        self.market_regime = market_regime
        
        # Actualizar historiales
        self.price_history.append(price)
        self.volume_history.append(volume)
        self.ema_history['fast'].append(ema_fast)
        self.ema_history['slow'].append(ema_slow)
        self.ema_history['trend'].append(ema_trend)
        
        # Mantener solo los últimos 100 registros
        if len(self.price_history) > 100:
            self.price_history = self.price_history[-100:]
            self.volume_history = self.volume_history[-100:]
            for key in self.ema_history:
                self.ema_history[key] = self.ema_history[key][-100:]
        
        # Log a CSV para análisis
        try:
            with open(self.market_csv, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    timestamp.isoformat(), price, rsi, volume, ema_fast, ema_slow, 
                    ema_trend, trend_direction, signal or '', self.in_position,
                    self.position['side'] if self.position else '', unrealized_pnl, 
                    pending_signal, volatility, market_regime, self.avg_volume
                ])
        except Exception as e:
            self.logger.error(f"Error guardando datos de mercado: {e}")
    
    def save_bot_state(self):
        """Guarda el estado actual del bot en archivo JSON"""
        try:
            def serialize_datetime(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                elif isinstance(obj, dict):
                    return {k: serialize_datetime(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [serialize_datetime(item) for item in obj]
                else:
                    return obj
            
            state_data = {
                'timestamp': datetime.now().isoformat(),
                'in_position': self.in_position,
                'position': serialize_datetime(self.position) if self.position else None,
                'last_signal_time': self.last_signal_time,
                'pending_long_signal': self.pending_long_signal,
                'pending_short_signal': self.pending_short_signal,
                'signal_trigger_price': self.signal_trigger_price,
                'signal_trigger_time': self.signal_trigger_time.isoformat() if self.signal_trigger_time else None,
                'signal_confidence': self.signal_confidence,
                'swing_wait_count': self.swing_wait_count,
                'performance_metrics': self.performance_metrics,
                'last_rsi': self.last_rsi,
                'last_price': self.last_price,
                'last_ema_fast': self.last_ema_fast,
                'last_ema_slow': self.last_ema_slow,
                'last_ema_trend': self.last_ema_trend,
                'trend_direction': self.trend_direction,
                'market_regime': self.market_regime,
                'current_volatility': self.current_volatility,
                'avg_volume': self.avg_volume
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(state_data, f, indent=2, default=str)
                
        except Exception as e:
            self.logger.error(f"Error guardando estado del bot: {e}")
    
    def load_bot_state(self):
        """Carga el estado previo del bot desde archivo JSON"""
        try:
            if not os.path.exists(self.state_file):
                self.logger.info("📄 No hay archivo de estado previo")
                return False
                
            with open(self.state_file, 'r') as f:
                state_data = json.load(f)
            
            # Verificar que el estado no sea muy antiguo
            state_time = datetime.fromisoformat(state_data['timestamp'])
            time_diff = datetime.now() - state_time
            
            if time_diff.total_seconds() > 172800:  # 48 horas
                self.logger.warning(f"⏰ Estado muy antiguo ({time_diff}), no se cargará")
                return False
            
            # Restaurar estado básico
            self.in_position = state_data.get('in_position', False)
            self.last_signal_time = state_data.get('last_signal_time', 0)
            self.pending_long_signal = state_data.get('pending_long_signal', False)
            self.pending_short_signal = state_data.get('pending_short_signal', False)
            self.signal_trigger_price = state_data.get('signal_trigger_price')
            self.signal_confidence = state_data.get('signal_confidence', 0)
            self.swing_wait_count = state_data.get('swing_wait_count', 0)
            
            # Restaurar datos de mercado
            self.last_rsi = state_data.get('last_rsi', 50)
            self.last_price = state_data.get('last_price', 0)
            self.last_ema_fast = state_data.get('last_ema_fast', 0)
            self.last_ema_slow = state_data.get('last_ema_slow', 0)
            self.last_ema_trend = state_data.get('last_ema_trend', 0)
            self.trend_direction = state_data.get('trend_direction', 'neutral')
            self.market_regime = state_data.get('market_regime', 'trending')
            self.current_volatility = state_data.get('current_volatility', 0)
            self.avg_volume = state_data.get('avg_volume', 0)
            
            # Restaurar signal_trigger_time
            if state_data.get('signal_trigger_time'):
                self.signal_trigger_time = datetime.fromisoformat(state_data['signal_trigger_time'])
            
            # Restaurar posición si existe
            if state_data.get('position'):
                self.position = state_data['position'].copy()
                if 'entry_time' in self.position:
                    self.position['entry_time'] = datetime.fromisoformat(self.position['entry_time'])
            
            # Restaurar métricas
            if state_data.get('performance_metrics'):
                self.performance_metrics.update(state_data['performance_metrics'])
            
            self.logger.info(f"📥 Estado del bot cargado desde {state_time.strftime('%H:%M:%S')}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error cargando estado del bot: {e}")
            return False
    
    def recover_bot_state(self):
        """Proceso completo de recuperación del estado del bot"""
        self.logger.info("🔄 Iniciando recuperación de estado...")
        
        # Intentar cargar estado desde archivo
        state_loaded = self.load_bot_state()
        
        # Verificar posiciones reales en el exchange
        exchange_position = self.check_exchange_positions()
        
        # Reconciliar estado
        if state_loaded and self.in_position and exchange_position:
            self.logger.info("✅ Estado y posición recuperados correctamente")
            
        elif not state_loaded and exchange_position:
            self.logger.warning("⚠️ Posición encontrada sin estado guardado - Recuperando...")
            self.recover_position_from_exchange(exchange_position)
            
        elif state_loaded and self.in_position and not exchange_position:
            self.logger.error("❌ Estado dice posición abierta pero no existe en exchange")
            self.logger.error("🔧 Limpiando estado inconsistente...")
            self.position = None
            self.in_position = False
            
        elif not state_loaded and not exchange_position:
            self.logger.info("✅ Bot limpio - Sin estado previo ni posiciones")
        
        # Guardar estado actualizado
        self.save_bot_state()
        
        self.logger.info("🔄 Recuperación completada")
    
    def check_exchange_positions(self):
        """Verifica posiciones reales en el exchange"""
        try:
            # Para futuros con apalancamiento
            try:
                if not self.testnet and self.leverage > 1:
                    self.exchange.set_sandbox_mode(False)
                    positions = self.exchange.fetch_positions([self.symbol])
                    
                    for pos in positions:
                        if pos['size'] > 0:
                            self.logger.warning(f"🔍 Posición detectada en exchange: {pos['side']} {pos['size']} @ {pos['entryPrice']}")
                            return pos
            except:
                pass
            
            # Para spot trading
            balance = self.exchange.fetch_balance()
            btc_balance = float(balance.get('BTC', {}).get('free', 0))
            
            if btc_balance > 0.001:
                ticker = self.exchange.fetch_ticker(self.symbol)
                current_price = ticker['last']
                
                self.logger.warning(f"🔍 Balance BTC detectado: {btc_balance:.6f} BTC (≈${btc_balance * current_price:.2f})")
                
                return {
                    'side': 'long',
                    'size': btc_balance,
                    'entryPrice': current_price,
                    'symbol': self.symbol
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error verificando posiciones en exchange: {e}")
            return None
    
    def recover_position_from_exchange(self, exchange_position):
        """Recupera una posición desde datos del exchange"""
        try:
            current_price = exchange_position.get('entryPrice', 0)
            quantity = exchange_position.get('size', 0)
            side = exchange_position.get('side', 'long')
            
            # Calcular stop loss y take profit basado en precio actual
            if side == 'long':
                stop_price = current_price * (1 - self.stop_loss_pct / 100)
                take_profit_price = current_price * (1 + self.take_profit_pct / 100)
            else:
                stop_price = current_price * (1 + self.stop_loss_pct / 100)
                take_profit_price = current_price * (1 - self.take_profit_pct / 100)
            
            # Crear posición para monitoreo
            self.position = {
                'side': side,
                'entry_price': current_price,
                'entry_time': datetime.now(),
                'quantity': quantity,
                'stop_loss': stop_price,
                'take_profit': take_profit_price,
                'order_id': f"recovered_{int(time.time())}",
                'entry_rsi': 50,
                'entry_confidence': 0.5,
                'recovered': True,
                'highest_price': current_price if side == 'long' else None,
                'lowest_price': current_price if side == 'short' else None,
                'trailing_stop': stop_price,
                'breakeven_moved': False
            }
            
            self.in_position = True
            
            # Log de recuperación
            with open(self.recovery_file, 'a') as f:
                f.write(f"{datetime.now().isoformat()} - Posición recuperada: {side} {quantity} @ ${current_price:.2f}\n")
            
            self.logger.warning(f"🔄 POSICIÓN RECUPERADA: {side.upper()} {quantity:.6f} BTC @ ${current_price:.2f}")
            self.logger.warning(f"📊 Nuevos niveles - SL: ${stop_price:.2f} | TP: ${take_profit_price:.2f}")
            
            self.performance_metrics['recoveries_performed'] += 1
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error recuperando posición: {e}")
            return False
    
    def init_log_files(self):
        """Inicializa archivos CSV para análisis"""
        self.trades_csv = os.path.join(self.logs_dir, f'optimized_trades_{datetime.now().strftime("%Y%m%d")}.csv')
        self.market_csv = os.path.join(self.logs_dir, f'optimized_market_data_{datetime.now().strftime("%Y%m%d")}.csv')
        
        # Headers para trades
        if not os.path.exists(self.trades_csv):
            with open(self.trades_csv, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'action', 'side', 'price', 'quantity', 'rsi', 
                    'ema_fast', 'ema_slow', 'ema_trend', 'trend_direction',
                    'stop_loss', 'take_profit', 'reason', 'pnl_pct', 'pnl_usdt',
                    'balance_before', 'balance_after', 'trade_duration_hours',
                    'signal_confirmed', 'confirmation_time_hours', 'pullback_type',
                    'entry_confidence', 'market_regime', 'volatility', 'volume_confirmed'
                ])
        
        # Headers para datos de mercado (ampliados)
        if not os.path.exists(self.market_csv):
            with open(self.market_csv, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'price', 'rsi', 'volume', 'ema_fast', 'ema_slow', 
                    'ema_trend', 'trend_direction', 'signal', 'in_position',
                    'position_side', 'unrealized_pnl_pct', 'pending_signal',
                    'volatility', 'market_regime', 'avg_volume'
                ])
    
    def get_account_balance(self):
        """Obtiene el balance de la cuenta"""
        try:
            balance = self.exchange.fetch_balance()
            usdt_balance = float(balance.get('USDT', {}).get('free', 0))
            return usdt_balance
        except Exception as e:
            self.logger.error(f"Error obteniendo balance: {e}")
            return 0
    
    def create_test_order(self, side, quantity, price):
        """Simula una orden para testnet"""
        order_id = f"optimized_test_{int(time.time())}"
        
        fake_order = {
            'id': order_id,
            'symbol': self.symbol,
            'side': side,
            'amount': quantity,
            'price': price,
            'status': 'closed',
            'filled': quantity,
            'timestamp': int(time.time() * 1000),
            'info': {'test_order': True}
        }
        
        self.logger.info(f"🧪 ORDEN SIMULADA: {side} {quantity} BTC @ ${price:.2f}")
        return fake_order
    
    def open_long_position(self, market_data, confirmation_time=None):
        """Abre posición LONG optimizada"""
        try:
            price = market_data['price']
            rsi = market_data['rsi']
            ema_fast = market_data['ema_fast']
            ema_slow = market_data['ema_slow']
            ema_trend = market_data['ema_trend']
            trend_direction = market_data['trend_direction']
            volatility = market_data['volatility']
            
            quantity, position_value = self.calculate_dynamic_position_size(
                price, self.signal_confidence, volatility
            )
            
            if quantity <= 0:
                self.logger.warning("⚠️ No se puede calcular tamaño de posición válido")
                return False
            
            # Calcular niveles de riesgo
            stop_price = price * (1 - self.stop_loss_pct / 100)
            take_profit_price = price * (1 + self.take_profit_pct / 100)
            
            # Intentar crear orden real
            try:
                if self.testnet:
                    order = self.exchange.create_market_order(self.symbol, 'buy', quantity)
                else:
                    order = self.exchange.create_market_order(self.symbol, 'buy', quantity)
            except Exception as order_error:
                self.logger.warning(f"Error creando orden real: {order_error}")
                order = self.create_test_order('buy', quantity, price)
            
            self.position = {
                'side': 'long',
                'entry_price': price,
                'entry_time': datetime.now(),
                'quantity': quantity,
                'stop_loss': stop_price,
                'take_profit': take_profit_price,
                'order_id': order['id'],
                'entry_rsi': rsi,
                'entry_confidence': self.signal_confidence,
                'entry_ema_fast': ema_fast,
                'entry_ema_slow': ema_slow,
                'entry_ema_trend': ema_trend,
                'entry_trend_direction': trend_direction,
                'entry_volatility': volatility,
                'entry_market_regime': market_data['market_regime'],
                'confirmation_time': confirmation_time,
                'recovered': False,
                'highest_price': price,
                'trailing_stop': stop_price,
                'breakeven_moved': False
            }
            
            self.in_position = True
            
            self.logger.info(f"🟢 LONG OPTIMIZADO EJECUTADO: {quantity:.6f} BTC @ ${price:.2f}")
            self.logger.info(f"📊 SL: ${stop_price:.2f} | TP: ${take_profit_price:.2f} | Confianza: {self.signal_confidence:.2f}")
            self.logger.info(f"🔄 Tendencia: {trend_direction} | RSI: {rsi:.1f} | Volatilidad: {volatility:.1f}%")
            self.logger.info(f"💰 Tamaño dinámico: {(quantity * price):.2f} USDT ({((quantity * price) / self.get_account_balance()) * 100:.1f}%)")
            
            # Log detallado del trade
            self.log_trade('OPEN', 'long', price, quantity, rsi, ema_fast, ema_slow, ema_trend, 
                          trend_direction, 'Optimized Long Entry', confirmation_time=confirmation_time,
                          confidence=self.signal_confidence, market_regime=market_data['market_regime'], 
                          volatility=volatility)
            
            self.save_bot_state()
            return True
            
        except Exception as e:
            self.logger.error(f"Error abriendo posición LONG: {e}")
            return False
    
    def open_short_position(self, market_data, confirmation_time=None):
        """Abre posición SHORT optimizada"""
        try:
            price = market_data['price']
            rsi = market_data['rsi']
            ema_fast = market_data['ema_fast']
            ema_slow = market_data['ema_slow']
            ema_trend = market_data['ema_trend']
            trend_direction = market_data['trend_direction']
            volatility = market_data['volatility']
            
            quantity, position_value = self.calculate_dynamic_position_size(
                price, self.signal_confidence, volatility
            )
            
            if quantity <= 0:
                self.logger.warning("⚠️ No se puede calcular tama
